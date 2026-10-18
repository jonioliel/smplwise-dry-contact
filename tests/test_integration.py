"""Flow and entity logic tests with explicit HA interface doubles."""

import importlib.util
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from tests import ha_fakes
from tests.support import COMPONENT, load_part

ha_fakes.install()
flow_api = load_part("config_flow")
client_api = load_part("client")
io_api = load_part("io")
coordinator_api = load_part("coordinator")
sensor_api = load_part("binary_sensor")
diagnostics_api = load_part("diagnostics")
spec = importlib.util.spec_from_file_location(
    "m31_test.entrypoint", COMPONENT / "__init__.py"
)
entrypoint = importlib.util.module_from_spec(spec)
entrypoint.__package__ = "m31_test"
spec.loader.exec_module(entrypoint)
INFO = client_api.ControllerInfo(
    "M31-AXXXA000G-U", 16, "02:11:22:33:44:55", "9232-0-13"
)


class FlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_initial_setup_normalizes_and_saves_expansion_inventory(self):
        flow = flow_api.M31ConfigFlow()
        with patch.object(flow_api, "_probe", AsyncMock(return_value=INFO)) as probe:
            result = await flow.async_step_user(
                {
                    "host": "192.168.99.99",
                    "model": "M31-AAAX4440G",
                    "expansion_models": "gxxax0080, M31-GXAXX0800",
                }
            )
        expected = ["GXXAX0080", "M31-GXAXX0800"]
        self.assertEqual(result["data"]["expansion_models"], expected)
        self.assertEqual(probe.await_args.args[0]["expansion_models"], expected)

    async def test_invalid_expansion_inventory_does_not_probe_or_save(self):
        flow = flow_api.M31ConfigFlow()
        with patch.object(flow_api, "_probe", AsyncMock()) as probe:
            result = await flow.async_step_user(
                {"host": "192.168.99.99", "expansion_models": "invalid"}
            )
        self.assertEqual(result["errors"], {"base": "invalid_expansions"})
        probe.assert_not_called()
        options = flow_api.M31OptionsFlow()
        options.config_entry = ha_fakes.Entry()
        with patch.object(flow_api, "_probe", AsyncMock()) as probe:
            result = await options.async_step_init(
                {
                    "scan_interval": 1,
                    "input_count": 0,
                    "inverted_inputs": "",
                    "expansion_models": "invalid",
                }
            )
        self.assertEqual(result["errors"], {"base": "invalid_expansions"})
        probe.assert_not_called()

    async def test_options_can_replace_or_clear_initial_expansion_inventory(self):
        entry = ha_fakes.Entry()
        entry.data["expansion_models"] = ["GXXAX0080"]
        for text, expected in (("GXAXX0800", ["GXAXX0800"]), ("", [])):
            with self.subTest(inventory=text):
                flow = flow_api.M31OptionsFlow()
                flow.config_entry = entry
                form = await flow.async_step_init()
                data = form["data_schema"](
                    {
                        "scan_interval": 1,
                        "input_count": 0,
                        "inverted_inputs": "",
                        "expansion_models": text,
                    }
                )
                with patch.object(
                    flow_api, "_probe", AsyncMock(return_value=INFO)
                ) as probe:
                    result = await flow.async_step_init(data)
                self.assertEqual(result["data"]["expansion_models"], expected)
                self.assertEqual(probe.await_args.args[0]["expansion_models"], expected)

    async def test_reconfigure_keeps_options_inventory(self):
        flow = flow_api.M31ConfigFlow()
        flow.entry = ha_fakes.Entry(options={"expansion_models": ["GXXAX0080"]})
        with patch.object(flow_api, "_probe", AsyncMock(return_value=INFO)) as probe:
            result = await flow.async_step_reconfigure({"host": "192.168.99.100"})
        self.assertEqual(result["reason"], "reconfigure_successful")
        self.assertEqual(flow.entry.data["expansion_models"], ["GXXAX0080"])
        self.assertEqual(probe.await_args.args[0]["expansion_models"], ["GXXAX0080"])

    async def test_duplicate_endpoint_with_changed_inventory_is_not_probed(self):
        flow = flow_api.M31ConfigFlow()
        flow.entries = [ha_fakes.Entry()]
        with (
            patch.object(flow_api, "_probe", AsyncMock()) as probe,
            self.assertRaises(ha_fakes.AbortFlow),
        ):
            await flow.async_step_user(
                {
                    "host": "192.168.99.99",
                    "model": "M31-AAAX4440G",
                    "expansion_models": "GXXAX0080",
                }
            )
        probe.assert_not_called()

    async def test_legacy_model_is_saved_with_connection(self):
        flow = flow_api.M31ConfigFlow()
        data = {"host": "192.168.99.99", "model": "M31-AXXXA000G"}
        with patch.object(flow_api, "_probe", AsyncMock(return_value=INFO)) as probe:
            result = await flow.async_step_user(data)
        self.assertEqual(result["data"]["model"], "M31-AXXXA000G")
        self.assertEqual(probe.await_args.args[0]["model"], "M31-AXXXA000G")

    async def test_missing_model_register_prompts_for_model(self):
        flow = flow_api.M31ConfigFlow()
        with patch.object(
            flow_api,
            "_probe",
            AsyncMock(side_effect=client_api.ModelRequired("select")),
        ):
            result = await flow.async_step_user({"host": "192.168.99.99"})
        self.assertEqual(result["errors"], {"model": "model_required"})
        self.assertEqual(
            result["data_schema"]({"host": "192.168.99.99", "model": "M31-AXXXA000G"})[
                "model"
            ],
            "M31-AXXXA000G",
        )

    async def test_probe_passes_legacy_model_hint(self):
        client = Mock(identify=AsyncMock(return_value=INFO))
        with patch.object(flow_api, "M31Client", return_value=client):
            await flow_api._probe(
                {
                    "host": "192.168.99.99",
                    "port": 502,
                    "unit_id": 1,
                    "model": "M31-AXXX8000G",
                },
                24,
            )
        client.identify.assert_awaited_once_with(24, model_hint="M31-AXXX8000G")
        client.close.assert_called_once()

    async def test_reconfigure_retains_selected_legacy_model(self):
        flow = flow_api.M31ConfigFlow()
        flow.entry = ha_fakes.Entry(
            data={
                "host": "192.168.99.99",
                "port": 502,
                "unit_id": 1,
                "model": "M31-AXXXA000G",
            }
        )
        with patch.object(flow_api, "_probe", AsyncMock(return_value=INFO)) as probe:
            result = await flow.async_step_reconfigure({"host": "192.168.99.100"})
        self.assertEqual(result["reason"], "reconfigure_successful")
        self.assertEqual(flow.entry.data["model"], "M31-AXXXA000G")
        self.assertEqual(probe.await_args.args[0]["model"], "M31-AXXXA000G")

    async def test_reconfigure_can_clear_a_model_hint(self):
        flow = flow_api.M31ConfigFlow()
        flow.entry = ha_fakes.Entry(
            data={
                "host": "192.168.99.99",
                "port": 502,
                "unit_id": 1,
                "model": "M31-AXXXA000G",
            }
        )
        with patch.object(flow_api, "_probe", AsyncMock(return_value=INFO)):
            await flow.async_step_reconfigure(
                {"host": "192.168.99.99", "model": "auto"}
            )
        self.assertNotIn("model", flow.entry.data)

    async def test_initial_form_and_ip_only_success(self):
        flow = flow_api.M31ConfigFlow()
        form = await flow.async_step_user()
        self.assertEqual(
            form["data_schema"]({"host": "192.168.99.99"}),
            {"host": "192.168.99.99", "model": "auto"},
        )
        with patch.object(flow_api, "_probe", AsyncMock(return_value=INFO)) as probe:
            result = await flow.async_step_user({"host": "192.168.99.99"})
        self.assertEqual(result["type"], "create_entry")
        self.assertEqual(
            result["data"], {"host": "192.168.99.99", "port": 502, "unit_id": 1}
        )
        self.assertEqual(flow.unique_id, INFO.mac)
        probe.assert_awaited_once_with(result["data"], 0)

    async def test_invalid_ip_is_rejected_without_network(self):
        with patch.object(flow_api, "_probe", AsyncMock()) as probe:
            result = await flow_api.M31ConfigFlow().async_step_user(
                {"host": "http://192.168.99.99"}
            )
        self.assertEqual(result["errors"], {"host": "invalid_host"})
        probe.assert_not_called()

    async def test_unreachable_controller_can_be_retried(self):
        flow = flow_api.M31ConfigFlow()
        with patch.object(
            flow_api, "_probe", AsyncMock(side_effect=client_api.M31Error("offline"))
        ):
            result = await flow.async_step_user({"host": "192.168.99.99"})
        self.assertEqual(result["errors"], {"base": "cannot_connect"})
        with patch.object(flow_api, "_probe", AsyncMock(return_value=INFO)):
            self.assertEqual(
                (await flow.async_step_user({"host": "192.168.99.99"}))["type"],
                "create_entry",
            )

    async def test_unknown_model_exposes_manual_count(self):
        flow = flow_api.M31ConfigFlow()
        with patch.object(
            flow_api,
            "_probe",
            AsyncMock(side_effect=client_api.UnsupportedModel("new")),
        ):
            form = await flow.async_step_user({"host": "192.168.99.99"})
        self.assertEqual(form["errors"]["base"], "unsupported_model")
        data = form["data_schema"]({"host": "192.168.99.99", "input_count": 16})
        with patch.object(flow_api, "_probe", AsyncMock(return_value=INFO)) as probe:
            result = await flow.async_step_user(data)
        self.assertEqual(result["options"]["input_count"], 16)
        self.assertEqual(probe.await_args.args[1], 16)

    async def test_duplicate_endpoint_is_rejected_before_probe(self):
        flow = flow_api.M31ConfigFlow()
        flow.entries = [ha_fakes.Entry()]
        with (
            patch.object(flow_api, "_probe", AsyncMock()) as probe,
            self.assertRaises(ha_fakes.AbortFlow),
        ):
            await flow.async_step_user({"host": "192.168.99.99"})
        probe.assert_not_called()

    async def test_duplicate_mac_at_new_ip_is_rejected(self):
        flow = flow_api.M31ConfigFlow()
        flow.entries = [ha_fakes.Entry()]
        with (
            patch.object(flow_api, "_probe", AsyncMock(return_value=INFO)),
            self.assertRaises(ha_fakes.AbortFlow),
        ):
            await flow.async_step_user({"host": "192.168.99.100"})

    async def test_ipv6_and_no_mac_identity(self):
        info = client_api.ControllerInfo(INFO.model, 16)
        flow = flow_api.M31ConfigFlow()
        with patch.object(flow_api, "_probe", AsyncMock(return_value=info)):
            await flow.async_step_user({"host": "[fd00::42]"})
        self.assertEqual(flow.unique_id, "fd00::42:502:1")

    async def test_reconfigure_preserves_identity_and_custom_title(self):
        flow = flow_api.M31ConfigFlow()
        flow.entry = ha_fakes.Entry()
        flow.entry.title = "My controller"
        with patch.object(flow_api, "_probe", AsyncMock(return_value=INFO)):
            result = await flow.async_step_reconfigure({"host": "192.168.99.100"})
        self.assertEqual(result["reason"], "reconfigure_successful")
        self.assertEqual(flow.entry.unique_id, INFO.mac)
        self.assertEqual(flow.entry.title, "My controller")
        self.assertEqual(flow.entry.data["host"], "192.168.99.100")

    async def test_reconfigure_rejects_different_hardware(self):
        flow = flow_api.M31ConfigFlow()
        flow.entry = ha_fakes.Entry()
        info = client_api.ControllerInfo(INFO.model, 16, "aa:bb:cc:dd:ee:ff")
        with patch.object(flow_api, "_probe", AsyncMock(return_value=info)):
            result = await flow.async_step_reconfigure({"host": "192.168.99.100"})
        self.assertEqual(result["reason"], "wrong_device")
        self.assertEqual(flow.entry.data["host"], "192.168.99.99")

    async def test_endpoint_fallback_survives_repeated_ip_changes(self):
        flow = flow_api.M31ConfigFlow()
        flow.entry = ha_fakes.Entry(unique_id="192.168.99.99:502:1")
        with patch.object(flow_api, "_probe", AsyncMock(return_value=INFO)):
            for host in ("192.168.99.100", "192.168.99.101"):
                self.assertEqual(
                    (await flow.async_step_reconfigure({"host": host}))["reason"],
                    "reconfigure_successful",
                )
        self.assertEqual(flow.entry.unique_id, "192.168.99.99:502:1")

    async def test_options_inversion_and_polling(self):
        flow = flow_api.M31ConfigFlow.async_get_options_flow(ha_fakes.Entry())
        flow.config_entry = ha_fakes.Entry()
        form = await flow.async_step_init()
        data = form["data_schema"](
            {"scan_interval": 2, "input_count": 0, "inverted_inputs": "1, 16, 1"}
        )
        with patch.object(flow_api, "_probe", AsyncMock(return_value=INFO)):
            result = await flow.async_step_init(data)
        self.assertEqual(result["data"]["inverted_inputs"], [1, 16])
        self.assertEqual(result["data"]["scan_interval"], 2)

    async def test_invalid_inversion_does_not_save(self):
        for text in ("abc", "0", "17", "-1"):
            flow = flow_api.M31OptionsFlow()
            flow.config_entry = ha_fakes.Entry()
            with patch.object(flow_api, "_probe", AsyncMock(return_value=INFO)):
                result = await flow.async_step_init(
                    {"scan_interval": 1, "input_count": 0, "inverted_inputs": text}
                )
            self.assertEqual(result["errors"], {"inverted_inputs": "invalid_inputs"})

    async def test_probe_always_closes_client(self):
        client = Mock(identify=AsyncMock(side_effect=client_api.M31Error("offline")))
        with (
            patch.object(flow_api, "M31Client", return_value=client),
            self.assertRaises(client_api.M31Error),
        ):
            await flow_api._probe(ha_fakes.Entry().data)
        client.close.assert_called_once()


class LifecycleTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.hass = SimpleNamespace(
            config_entries=SimpleNamespace(
                async_forward_entry_setups=AsyncMock(),
                async_unload_platforms=AsyncMock(return_value=True),
                async_reload=AsyncMock(),
            )
        )
        self.entry = ha_fakes.Entry(
            options={"inverted_inputs": [2], "scan_interval": 2}
        )
        self.client = Mock(
            identify=AsyncMock(return_value=INFO),
            read_io=AsyncMock(
                return_value=io_api.IOState(di=(True, False) + (False,) * 14)
            ),
        )

    async def test_setup_entities_states_inversion_unload(self):
        with patch.object(entrypoint, "M31Client", return_value=self.client):
            self.assertTrue(await entrypoint.async_setup_entry(self.hass, self.entry))
        self.assertEqual(self.entry.runtime_data.update_interval.total_seconds(), 2)
        entities = []
        await sensor_api.async_setup_entry(self.hass, self.entry, entities.extend)
        self.assertEqual(len(entities), 16)
        self.assertTrue(entities[0].is_on)
        self.assertTrue(entities[1].is_on)  # raw False becomes on for NC contact
        self.assertFalse(entities[2].is_on)
        self.assertEqual(entities[15]._attr_unique_id, "02:11:22:33:44:55_di_16")
        self.entry.runtime_data.last_update_success = False
        self.assertFalse(entities[0].available)
        self.assertTrue(await entrypoint.async_unload_entry(self.hass, self.entry))
        for callback in self.entry.callbacks:
            callback()
        self.client.close.assert_called_once()

    async def test_startup_reuses_saved_legacy_model(self):
        self.entry.data["model"] = "M31-AXXXA000G"
        with patch.object(entrypoint, "M31Client", return_value=self.client):
            await entrypoint.async_setup_entry(self.hass, self.entry)
        self.client.identify.assert_awaited_once_with(0, model_hint="M31-AXXXA000G")
        self.client.close()

    async def test_startup_uses_inventory_saved_during_initial_setup(self):
        self.entry.data["expansion_models"] = ["GXXAX0080"]
        with patch.object(entrypoint, "M31Client", return_value=self.client):
            await entrypoint.async_setup_entry(self.hass, self.entry)
        self.client.identify.assert_awaited_once_with(
            0, model_hint=None, expansion_models=("GXXAX0080",)
        )
        self.client.close()

    async def test_empty_options_inventory_clears_initial_inventory(self):
        self.entry.data["expansion_models"] = ["GXXAX0080"]
        self.entry.options["expansion_models"] = []
        with patch.object(entrypoint, "M31Client", return_value=self.client):
            await entrypoint.async_setup_entry(self.hass, self.entry)
        self.client.identify.assert_awaited_once_with(0, model_hint=None)
        self.client.close()

    async def test_identification_failure_is_retryable_and_closes_socket(self):
        self.client.identify.side_effect = client_api.M31Error("offline")
        with (
            patch.object(entrypoint, "M31Client", return_value=self.client),
            self.assertRaises(ha_fakes.ConfigEntryNotReady),
        ):
            await entrypoint.async_setup_entry(self.hass, self.entry)
        self.client.close.assert_called_once()
        self.hass.config_entries.async_forward_entry_setups.assert_not_called()

    async def test_first_refresh_failure_closes_socket(self):
        self.client.read_io.side_effect = client_api.M31Error("offline")
        with (
            patch.object(entrypoint, "M31Client", return_value=self.client),
            self.assertRaises(ha_fakes.ConfigEntryNotReady),
        ):
            await entrypoint.async_setup_entry(self.hass, self.entry)
        self.client.close.assert_called_once()

    async def test_runtime_failure_is_update_failed(self):
        coordinator = coordinator_api.M31Coordinator(
            self.hass, self.entry, self.client, INFO
        )
        self.client.read_io.side_effect = client_api.M31Error("bus fault")
        with self.assertRaises(ha_fakes.UpdateFailed):
            await coordinator._async_update_data()

    async def test_diagnostics_excludes_identity_and_input_states(self):
        coordinator = coordinator_api.M31Coordinator(
            self.hass, self.entry, self.client, INFO
        )
        self.entry.runtime_data = coordinator
        data = await diagnostics_api.async_get_config_entry_diagnostics(
            self.hass, self.entry
        )
        text = json.dumps(data)
        self.assertNotIn("192.168.99.99", text)
        self.assertNotIn(INFO.mac, text)
        self.assertNotIn("inverted_inputs", text)
        self.assertEqual(data["input_count"], 16)

    async def test_options_reload(self):
        await entrypoint._async_update_options(self.hass, self.entry)
        self.hass.config_entries.async_reload.assert_awaited_once_with(
            self.entry.entry_id
        )


class TranslationTests(unittest.TestCase):
    def test_translations_have_identical_keys_and_valid_json(self):
        def keys(value, prefix=""):
            result = set()
            for key, item in value.items():
                path = f"{prefix}.{key}"
                result.add(path)
                if isinstance(item, dict):
                    result.update(keys(item, path))
            return result

        source = json.loads((COMPONENT / "strings.json").read_text(encoding="utf-8"))
        for language in ("en", "he"):
            translated = json.loads(
                (COMPONENT / "translations" / f"{language}.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(keys(source), keys(translated))
