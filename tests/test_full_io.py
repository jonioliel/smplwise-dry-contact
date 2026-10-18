"""Full IO maps and output controls, verified against both supplied manuals."""

import unittest
from unittest.mock import AsyncMock, Mock

from tests import ha_fakes
from tests.support import ModbusSimulator, load_part, string_registers

api = load_part("client")
models = load_part("models")
io = load_part("io")

# DI, DO, AI, AO, PT100; independent reference from the product tables.
CATALOG = {
    "M31-AAAX4440G": (4, 4, 4, 0, 0),
    "M31-AXXX8000G": (8, 0, 0, 0, 0),
    "M31-XXAX0080G": (0, 8, 0, 0, 0),
    "M31-AXAX4040G": (4, 4, 0, 0, 0),
    "M31-AXXXA000G": (16, 0, 0, 0, 0),
    "M31-XXAX00A0G": (0, 16, 0, 0, 0),
    "M31-AXAX8080G": (8, 8, 0, 0, 0),
    "M31-XAXX0800G": (0, 0, 8, 0, 0),
    "M31-XXXA0008G": (0, 0, 0, 8, 0),
    "M31-XAXA0404G": (0, 0, 4, 4, 0),
    "M31-XFXX0800G": (0, 0, 8, 0, 0),
    "M31-XGXX0800G": (0, 0, 8, 0, 0),
    "M31-AFAX4440G-U": (4, 4, 4, 0, 0),
    "M31-AXAX8080G-U": (8, 8, 0, 0, 0),
    "M31-AXXX8000G-U": (8, 0, 0, 0, 0),
    "M31-AXXXA000G-U": (16, 0, 0, 0, 0),
    "M31-AXEX8080G-U": (8, 8, 0, 0, 0),
    "M31-XXAX00A0G-U": (0, 16, 0, 0, 0),
    "M31-XXEX00A0G-U": (0, 16, 0, 0, 0),
    "M31-AXAX4040G-U": (4, 4, 0, 0, 0),
    "M31-XFXX0800G-U": (0, 0, 8, 0, 0),
    "M31-XAXX0A00G-U": (0, 0, 16, 0, 0),
    "M31-XBXX0A00G-U": (0, 0, 16, 0, 0),
    "M31-XXXA0008G-U": (0, 0, 0, 8, 0),
    "M31-XXXB0008G-U": (0, 0, 0, 8, 0),
    "M31-XDXX0600G-U": (0, 0, 0, 0, 6),
}


class CatalogTests(unittest.TestCase):
    def test_every_host_and_corresponding_expansion(self):
        self.assertEqual(set(CATALOG), set(models.HOST_MODELS))
        for name, expected in CATALOG.items():
            core = name[4:].removesuffix("-U").removesuffix("G")
            card = "M31-G" + core + ("-U" if name.endswith("-U") else "")
            for value, module in ((name, False), (card, True)):
                with self.subTest(model=value):
                    layout = models.model_layout(value, module=module)
                    self.assertEqual(
                        (
                            layout.di,
                            layout.do,
                            len(layout.ai),
                            len(layout.ao),
                            layout.pt,
                        ),
                        expected,
                    )

    def test_voltage_and_current_are_distinguished(self):
        self.assertEqual(models.model_layout("M31-XGXX0800G").ai, ("voltage",) * 8)
        self.assertEqual(models.model_layout("M31-XFXX0800G").ai, ("current",) * 8)
        self.assertEqual(models.model_layout("M31-XXXB0008G-U").ao, ("voltage",) * 8)

    def test_8do_u_expansion_without_corresponding_catalog_host(self):
        self.assertEqual(models.model_layout("GXXAX0080-U", module=True).do, 8)

    def test_protocol_variants_and_inconsistent_encoding_are_rejected(self):
        for name in (
            "M31-AXXX8000G-U-PN",
            "M31-AXXX8000G-U-CAN",
            "M31-XXXX8000G",
            "M31-AYXX0800G",
        ):
            with self.subTest(model=name), self.assertRaises(api.UnsupportedModel):
                models.model_layout(name)

    def test_expansion_list_parsing(self):
        self.assertEqual(
            models.parse_expansions("GXXAX0080,\nM31-GXAXX0800"),
            ("GXXAX0080", "M31-GXAXX0800"),
        )
        with self.assertRaises(api.UnsupportedModel):
            models.parse_expansions("garbage")


class FullIOTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.server = ModbusSimulator()
        await self.server.start()
        self.client = api.M31Client("127.0.0.1", self.server.port, timeout=2)

    async def asyncTearDown(self):
        self.client.close()
        await self.server.stop()

    async def test_every_catalog_host_can_be_identified_without_writing(self):
        for name, expected in CATALOG.items():
            with self.subTest(model=name):
                self.server.set_registers(0x0DAC, (0,) * 32)
                if name in ("M31-XGXX0800G", "M31-XBXX0A00G-U"):
                    self.server.set_registers(0x0DAC, (5,) * expected[2])
                if name.endswith("-U"):
                    core = name[4:].removesuffix("G-U")
                    self.server.set_modules(["G" + core + "-U"])
                info = await self.client.identify(model_hint=name)
                layout = info.io_layout
                self.assertEqual(
                    (layout.di, layout.do, len(layout.ai), len(layout.ao), layout.pt),
                    expected,
                )
        self.assertEqual(self.server.writes, [])

    async def mixed(self):
        self.server.set_registers(0x0C20, string_registers("M31-AFAX4440G-U", 12))
        self.server.set_modules(
            ["GAFAX4440-U", "GXXEX00A0-U", "GXBXX0A00-U", "GXXXB0008-U", "GXDXX0600-U"]
        )
        self.server.set_registers(0x0DAC, (2,) * 4 + (5,) * 16)
        self.server.input_registers[0] = (-3200) & 65535
        self.server.input_registers[4] = 7250
        return await self.client.identify()

    async def test_mixed_base_and_expansions_keep_independent_offsets(self):
        info = await self.mixed()
        self.assertEqual(
            (
                info.input_count,
                info.io_layout.do,
                len(info.io_layout.ai),
                len(info.io_layout.ao),
                info.io_layout.pt,
            ),
            (4, 20, 20, 8, 6),
        )
        snapshot = await self.client.read_io(info)
        self.assertEqual(snapshot.ai[0], -3.2)
        self.assertEqual(snapshot.ai[4], 7.25)
        self.assertEqual(self.server.writes, [])

    async def test_digital_output_extension_write_and_readback(self):
        info = await self.mixed()
        await self.client.set_do(info, 19, True)
        self.assertEqual(self.server.writes, [(5, 19, 0xFF00)])
        self.assertTrue((await self.client.read_io(info)).do[19])
        await self.client.set_do(info, 19, False)
        self.assertFalse(self.server.coils[19])

    async def test_analog_extension_write_uses_fc16_and_correct_channel(self):
        info = await self.mixed()
        await self.client.set_ao(info, 7, 4.321)
        self.assertEqual(self.server.writes, [(16, 7, 4321)])
        state = await self.client.read_io(info)
        self.assertEqual(state.ao[7], 4.321)
        self.assertEqual(state.ao[0], 0)

    async def test_changed_ao_range_is_checked_at_command_time(self):
        info = await self.mixed()
        self.server.set_registers(0x1194, (1,))  # 0-5 V after initial 0-10 V read
        with self.assertRaises(ValueError):
            await self.client.set_ao(info, 0, 5.001)
        self.assertEqual(self.server.writes, [])
        await self.client.set_ao(info, 0, 5)

    async def test_current_output_respects_4_20_range(self):
        self.server.use_legacy_register_map()
        self.server.set_registers(0x1194, (1,) * 8)
        info = await self.client.identify(model_hint="M31-XXXA0008G")
        for value in (0, 3.999, 20.001):
            with self.assertRaises(ValueError):
                await self.client.set_ao(info, 0, value)
        self.assertEqual(self.server.writes, [])
        await self.client.set_ao(info, 0, 4)
        self.assertEqual(self.server.writes, [(16, 0, 4000)])

    async def test_non_finite_and_invalid_channel_values_never_write(self):
        info = await self.mixed()
        for value in (float("nan"), float("inf"), -float("inf"), True):
            with self.assertRaises(ValueError):
                await self.client.set_ao(info, 0, value)
        for index in (-1, 8):
            with self.assertRaises(ValueError):
                await self.client.set_ao(info, index, 1)
        with self.assertRaises(ValueError):
            await self.client.set_do(info, 20, True)
        self.assertEqual(self.server.writes, [])

    async def test_io_fault_blocks_all_output_commands(self):
        info = await self.mixed()
        self.server.set_registers(0x7587, (2,))
        for command in (
            self.client.set_do(info, 0, True),
            self.client.set_ao(info, 0, 2),
        ):
            with self.assertRaises(api.M31Error):
                await command
        self.assertEqual(self.server.writes, [])

    async def test_bad_write_echo_is_not_reported_as_success(self):
        info = await self.mixed()

        def corrupt(request, response):
            return (
                response[:-1] + bytes([response[-1] ^ 1])
                if request[7] in (5, 16)
                else response
            )

        self.server.hook = corrupt
        with self.assertRaises(api.M31Error):
            await self.client.set_do(info, 0, True)
        with self.assertRaises(api.M31Error):
            await self.client.set_ao(info, 0, 2)

    async def test_pt100_units_and_diagnostic_sentinels(self):
        info = await self.mixed()
        self.server.set_registers(0x39A4, (0, 1, 2, 0, 0, 0))
        raw = (250, 770, 2981, 32766, (-32766) & 65535, 32765)
        self.server.input_registers.update({0x0DAC + i: v for i, v in enumerate(raw)})
        state = await self.client.read_io(info)
        self.assertEqual(state.pt, (25.0, 25.0, 24.95, None, None, None))
        self.assertEqual(
            state.pt_status[3:], ("disconnected", "short_circuit", "chip_fault")
        )

    async def test_legacy_manual_mixed_inventory(self):
        self.server.use_legacy_register_map(8)
        info = await self.client.identify(
            model_hint="M31-AXXX8000G", expansion_models=("GXXAX0080", "GXAXA0404")
        )
        self.assertEqual(
            (
                info.io_layout.di,
                info.io_layout.do,
                len(info.io_layout.ai),
                len(info.io_layout.ao),
            ),
            (8, 8, 4, 4),
        )
        self.assertEqual(info.inventory_source, "manual")
        self.assertFalse(
            any(0x0C20 <= address < 0x0D80 for _, _, address, _ in self.server.requests)
        )

    async def test_mismatched_extension_series_is_rejected(self):
        with self.assertRaises(api.UnsupportedModel):
            await self.client.identify(
                model_hint="M31-AXXX8000G", expansion_models=("GXXAX0080-U",)
            )

    async def test_large_analog_reads_are_split_at_125_registers(self):
        modules = ("GXAXX0A00-U",) * 8
        self.server.set_modules(["GAXXXA000-U", *modules])
        info = await self.client.identify()
        self.assertEqual(len(info.io_layout.ai), 128)
        self.assertIn((1, 4, 0, 125), self.server.requests)
        self.assertIn((1, 4, 125, 3), self.server.requests)

    async def test_snapshots_and_commands_are_serialized(self):
        import asyncio

        info = await self.mixed()
        await asyncio.gather(
            self.client.read_io(info),
            self.client.set_do(info, 2, True),
            self.client.set_ao(info, 2, 3),
        )
        state = await self.client.read_io(info)
        self.assertTrue(state.do[2])
        self.assertEqual(state.ao[2], 3)


class EntityControlTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        ha_fakes.install()
        self.entry = ha_fakes.Entry()
        layout = models.IOLayout(di=1, do=1, ai=("current",), ao=("voltage",), pt=1)
        self.info = api.ControllerInfo("mixed", 1, layout=layout)
        self.client = Mock(set_do=AsyncMock(), set_ao=AsyncMock())
        self.coordinator = Mock(
            info=self.info,
            identity="stable",
            client=self.client,
            last_update_success=True,
            async_request_refresh=AsyncMock(),
        )
        self.coordinator.data = io.IOState(
            di=(True,),
            do=(False,),
            ai=(-2.5,),
            ao=(1.5,),
            ao_ranges=(1,),
            pt=(None,),
            pt_status=("disconnected",),
        )

    async def test_switch_command_refreshes_and_preserves_readback(self):
        entity = load_part("switch").M31Output(self.coordinator, self.entry, 0)
        await entity.async_turn_on()
        self.client.set_do.assert_awaited_once_with(self.info, 0, True)
        self.coordinator.async_request_refresh.assert_awaited_once()
        self.assertFalse(entity.is_on)

    async def test_analog_number_uses_live_bounds_and_units(self):
        entity = load_part("number").M31AnalogOutput(
            self.coordinator, self.entry, 0, "voltage"
        )
        self.assertEqual((entity.native_min_value, entity.native_max_value), (0, 5))
        self.assertEqual(entity._attr_native_unit_of_measurement, "V")
        await entity.async_set_native_value(2.5)
        self.client.set_ao.assert_awaited_once_with(self.info, 0, 2.5)

    async def test_command_failure_becomes_home_assistant_error(self):
        self.client.set_do.side_effect = api.M31Error("failed")
        entity = load_part("switch").M31Output(self.coordinator, self.entry, 0)
        with self.assertRaises(ha_fakes.HomeAssistantError):
            await entity.async_turn_on()
        self.coordinator.async_request_refresh.assert_not_called()

    async def test_pt100_fault_only_makes_its_channel_unavailable(self):
        module = load_part("sensor")
        pt = module.M31Temperature(self.coordinator, self.entry, 0)
        ai = module.M31AnalogInput(self.coordinator, self.entry, 0, "current")
        self.assertFalse(pt.available)
        self.assertTrue(ai.available)
        self.assertEqual(ai.native_value, -2.5)

    async def test_unavailable_outputs_do_not_send_commands(self):
        self.coordinator.last_update_success = False
        entity = load_part("number").M31AnalogOutput(
            self.coordinator, self.entry, 0, "voltage"
        )
        with self.assertRaises(ha_fakes.HomeAssistantError):
            await entity.async_set_native_value(2.5)
        self.client.set_ao.assert_not_called()
