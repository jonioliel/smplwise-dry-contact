"""End-to-end transport tests using TCP, without Home Assistant installed."""

import asyncio
import struct
import unittest

from tests.support import ModbusSimulator, load_part, string_registers

api = load_part("client")


class ModelTests(unittest.TestCase):
    def test_documented_host_counts(self):
        for model, count in (
            ("M31-AXXXA000G-U", 16),
            ("M31-AXXX8000G-U", 8),
            ("M31-AXEX8080G-U", 8),
            ("M31-AFAX4440G-U", 4),
            ("M31-AXXXA000G", 16),
            ("M31-AXXX8000G", 8),
            ("M31-AXAX4040G", 4),
            ("M31-AXAX8080G", 8),
            ("M31-AAAX4440G", 4),
        ):
            with self.subTest(model=model):
                self.assertEqual(api.inputs_for_model(model), count)

    def test_unknown_or_output_only_host_is_rejected(self):
        for model in (
            "unknown",
            "M31-AXXXA000G-CAN",
            "M31-AXXXA000G-U-PN",
            "M31-XXAX00A0G-U",
        ):
            with self.subTest(model=model), self.assertRaises(api.UnsupportedModel):
                api.inputs_for_model(model)

    def test_modules_with_and_without_digital_inputs(self):
        self.assertEqual(api.inputs_for_module("GAXXXA000-U"), 16)
        self.assertEqual(api.inputs_for_module("M31-GAXEX8080-U"), 8)
        self.assertEqual(api.inputs_for_module("GXXAX00A0-U"), 0)
        with self.assertRaises(api.UnsupportedModel):
            api.inputs_for_module("unknown")


class ClientTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.server = ModbusSimulator()
        await self.server.start()
        self.client = api.M31Client("127.0.0.1", self.server.port, timeout=0.5)

    async def asyncTearDown(self):
        self.client.close()
        await self.server.stop()

    async def test_identify_does_not_duplicate_internal_card(self):
        info = await self.client.identify()
        self.assertEqual(info.input_count, 16)
        self.assertEqual(info.modules, ("GAXXXA000-U",))
        self.assertEqual(info.model, "M31-AXXXA000G-U")
        self.assertEqual(info.mac, "02:11:22:33:44:55")
        self.assertEqual(info.firmware, "9232-0-13")

    async def test_expansion_inputs_are_counted_in_bus_order(self):
        self.server.set_modules(["GAXXXA000-U", "GAXXXA000-U", "GXXAX00A0-U"])
        self.server.inputs *= 2
        info = await self.client.identify()
        self.assertEqual(info.input_count, 32)
        self.assertEqual(len(info.modules), 3)
        self.assertIn((1, 2, 0, 32), self.server.requests)

    async def test_inventory_crosses_frame_boundary(self):
        self.server.set_modules(["GAXXXA000-U"] * 9)
        self.server.inputs *= 9
        self.assertEqual((await self.client.identify()).input_count, 144)
        self.assertIn((1, 3, 0x0CC0, 64), self.server.requests)

    async def test_inventory_slot_zero_must_match_host(self):
        self.server.set_modules(["GAXXX8000-U"])
        with self.assertRaises(api.UnsupportedModel):
            await self.client.identify()

    async def test_unrecognized_expansion_requires_manual_count(self):
        self.server.set_modules(["GAXXXA000-U", "new-card"])
        with self.assertRaises(api.UnsupportedModel):
            await self.client.identify()
        self.assertEqual((await self.client.identify(16)).input_count, 16)

    async def test_older_firmware_without_inventory_uses_host(self):
        del self.server.registers[0x0C80]
        info = await self.client.identify()
        self.assertEqual(info.input_count, 16)
        self.assertEqual(info.modules, ())

    async def test_optional_metadata_can_be_absent(self):
        del self.server.registers[0x7534]
        del self.server.registers[0x0C2C]
        info = await self.client.identify()
        self.assertIsNone(info.mac)
        self.assertIsNone(info.firmware)

    async def test_manual_count_allows_firmware_without_model_register(self):
        del self.server.registers[0x0C20]
        with self.assertRaises(api.ModelRequired):
            await self.client.identify()
        self.assertEqual((await self.client.identify(16)).model, "M31 (manual)")

    async def test_manual_count_is_validated_by_real_input_read(self):
        with self.assertRaises(api.ModbusError):
            await self.client.identify(32)

    async def test_bit_order_and_byte_boundary(self):
        for index in (0, 7, 8, 15):
            self.server.inputs[index] = True
        states = await self.client.read_inputs(16)
        self.assertEqual(
            [i + 1 for i, state in enumerate(states) if state], [1, 8, 9, 16]
        )

    async def test_padding_bits_are_not_exposed(self):
        self.server.inputs = [True] * 16
        states = await self.client.read_inputs(9)
        self.assertEqual(states, (True,) * 9)

    async def test_fragmented_tcp_response(self):
        self.server.fragment = True
        self.client.timeout = 5
        self.assertEqual((await self.client.identify()).input_count, 16)

    async def test_bus_fault_never_becomes_an_off_state(self):
        for fault in (1, 2):
            self.server.set_registers(0x7587, (fault,))
            with self.subTest(fault=fault), self.assertRaises(api.M31Error):
                await self.client.read_state(16)
        self.assertTrue(all(request[1] == 3 for request in self.server.requests))
        self.server.set_registers(0x7587, (0,))
        self.assertEqual(await self.client.read_state(16), (False,) * 16)

    async def test_exception_frame_keeps_socket_usable(self):
        with self.assertRaises(api.ModbusError) as error:
            await self.client.read_registers(0xFFFF, 1)
        self.assertEqual(error.exception.code, 2)
        await self.client.read_inputs(16)
        self.assertEqual(self.server.connections, 1)

    async def test_invalid_headers_are_rejected_and_reconnected(self):
        for offset, value in ((0, 99), (2, 1), (4, 255), (6, 2)):

            def corrupt(request, response, offset=offset, value=value):
                changed = bytearray(response)
                if offset == 6:
                    changed[6] = value
                else:
                    struct.pack_into(">H", changed, offset, value)
                return bytes(changed)

            self.server.hook = corrupt
            with self.subTest(offset=offset), self.assertRaises(api.M31Error):
                await self.client.read_inputs(16)
            self.assertIsNone(self.client._writer)
            self.server.hook = None
            await self.client.read_inputs(16)

    async def test_wrong_function_and_byte_count(self):
        for offset, value in ((7, 3), (8, 0)):

            def corrupt(request, response, offset=offset, value=value):
                changed = bytearray(response)
                changed[offset] = value
                return bytes(changed)

            self.server.hook = corrupt
            with self.subTest(offset=offset), self.assertRaises(api.M31Error):
                await self.client.read_inputs(16)
            self.server.hook = None

    async def test_valid_byte_count_but_truncated_di_payload(self):
        def corrupt(request, response):
            return response[:4] + struct.pack(">H", 4) + response[6:8] + b"\x01\x00"

        self.server.hook = corrupt
        with self.assertRaises(api.M31Error):
            await self.client.read_inputs(16)
        self.assertIsNone(self.client._writer)

    async def test_register_payload_size_checked(self):
        self.server.hook = lambda request, response: (
            response[:4] + struct.pack(">H", 5) + response[6:8] + b"\x02\x00\x00"
        )
        with self.assertRaises(api.M31Error):
            await self.client.read_registers(0x7534, 3)

    async def test_peer_disconnect_then_reconnect(self):
        self.server.hook = lambda request, response: None
        with self.assertRaises(api.M31Error):
            await self.client.read_inputs(16)
        self.server.hook = None
        await self.client.read_inputs(16)
        self.assertEqual(self.server.connections, 2)

    async def test_timeout_then_reconnect(self):
        self.client.timeout = 0.03
        self.server.delay = 0.1
        with self.assertRaises(api.M31Error):
            await self.client.read_inputs(16)
        self.assertIsNone(self.client._writer)
        self.server.delay = 0
        self.client.timeout = 0.5
        await self.client.read_inputs(16)

    async def test_cancellation_closes_connection(self):
        self.server.delay = 1
        task = asyncio.create_task(self.client.read_inputs(16))
        await asyncio.sleep(0.03)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertIsNone(self.client._writer)

    async def test_concurrent_requests_are_serialized(self):
        results = await asyncio.gather(
            *(self.client.read_inputs(16) for _ in range(10))
        )
        self.assertTrue(all(result == (False,) * 16 for result in results))
        self.assertEqual(self.server.connections, 1)

    async def test_invalid_ranges_rejected_before_network(self):
        for count in (0, 513):
            with self.assertRaises(ValueError):
                await self.client.read_inputs(count)
        for address, count in ((0, 126), (-1, 1), (65535, 2), (0, 0)):
            with self.assertRaises(ValueError):
                await self.client.read_registers(address, count)
        self.assertEqual(self.server.connections, 0)

    async def test_model_read_is_zero_based(self):
        self.server.set_registers(0x0C20, string_registers("M31-AXXX8000G-U", 12))
        self.server.set_modules(["GAXXX8000-U"])
        info = await self.client.identify()
        self.assertEqual(info.input_count, 8)
        self.assertEqual(self.server.requests[0], (1, 3, 0x0C20, 12))

    async def test_legacy_selection_uses_only_documented_registers(self):
        self.server.use_legacy_register_map()
        info = await self.client.identify(model_hint="M31-AXXXA000G")
        self.assertEqual(info.model, "M31-AXXXA000G")
        self.assertEqual(info.family, "m31")
        self.assertEqual(info.input_count, 16)
        self.assertEqual(info.mac, "02:11:22:33:44:55")
        self.assertIsNone(info.firmware)
        self.assertEqual(info.modules, ())
        self.assertEqual(
            self.server.requests,
            [
                (1, 3, 0x7534, 3),
                (1, 3, 0x7587, 1),
                (1, 2, 0, 16),
            ],
        )

    async def test_each_documented_legacy_di_model(self):
        for model, count in (
            ("M31-AAAX4440G", 4),
            ("M31-AXAX4040G", 4),
            ("M31-AXXX8000G", 8),
            ("M31-AXAX8080G", 8),
            ("M31-AXXXA000G", 16),
        ):
            with self.subTest(model=model):
                self.server.use_legacy_register_map(count)
                info = await self.client.identify(model_hint=model)
                self.assertEqual(info.input_count, count)
                self.assertIn((1, 2, 0, count), self.server.requests)

    async def test_legacy_auto_requests_model_selection(self):
        self.server.use_legacy_register_map()
        with self.assertRaises(api.ModelRequired):
            await self.client.identify()
        self.assertEqual(self.server.requests, [(1, 3, 0x0C20, 12)])

    async def test_zero_filled_model_requests_selection(self):
        self.server.set_registers(0x0C20, (0,) * 12)
        with self.assertRaises(api.ModelRequired):
            await self.client.identify()

    async def test_legacy_named_by_newer_firmware_is_accepted(self):
        self.server.use_legacy_register_map(8)
        self.server.set_registers(0x0C20, string_registers("M31-AXXX8000G", 12))
        info = await self.client.identify()
        self.assertEqual(info.model, "M31-AXXX8000G")
        self.assertEqual(info.family, "m31")
        self.assertEqual(info.input_count, 8)
        self.assertFalse(
            any(
                address in (0x0C80, 0x0C2C) for _, _, address, _ in self.server.requests
            )
        )

    async def test_legacy_expansions_use_explicit_total(self):
        self.server.use_legacy_register_map(32)
        info = await self.client.identify(32, model_hint="M31-AXXXA000G")
        self.assertEqual(info.input_count, 32)
        self.assertEqual(info.model, "M31-AXXXA000G")
        self.assertEqual(self.server.requests[-1], (1, 2, 0, 32))

    async def test_legacy_bit_states_and_io_faults(self):
        self.server.use_legacy_register_map()
        self.server.inputs[0] = self.server.inputs[15] = True
        await self.client.identify(model_hint="M31-AXXXA000G")
        states = await self.client.read_state(16)
        self.assertEqual([i + 1 for i, state in enumerate(states) if state], [1, 16])
        self.server.set_registers(0x7587, (2,))
        with self.assertRaises(api.M31Error):
            await self.client.read_state(16)

    async def test_legacy_wrong_larger_model_is_rejected_by_input_read(self):
        self.server.use_legacy_register_map(8)
        with self.assertRaises(api.ModbusError):
            await self.client.identify(model_hint="M31-AXXXA000G")

    async def test_unsupported_model_hint_never_contacts_controller(self):
        with self.assertRaises(api.UnsupportedModel):
            await self.client.identify(model_hint="M31-AXXXA000G-PN")
        self.assertEqual(self.server.connections, 0)

    async def test_legacy_without_mac_uses_no_unsupported_metadata(self):
        self.server.use_legacy_register_map()
        del self.server.registers[0x7534]
        info = await self.client.identify(model_hint="M31-AXXXA000G")
        self.assertIsNone(info.mac)
        self.assertEqual(info.input_count, 16)
