# Changelog

## 1.1.0

- Support the older M31 series: M31-AXXXA000G (16 DI), M31-AXXX8000G (8 DI), M31-AXAX4040G (4 DI), M31-AXAX8080G (8 DI), and M31-AAAX4440G (4 DI).
- Add a model selector to setup and reconfiguration. Keep `auto` for M31-U; select the printed model for older M31 controllers.
- Use only documented MAC, IO fault and DI registers when an older M31 model is selected. Avoid unsupported M31-U identification, firmware and module inventory queries.
- Allow an explicit total DI count for older M31 expansion cards. Older M31 expansion discovery is not documented and is not assumed.
- Preserve existing M31-U connections, entity identities and input inversion settings.

## 1.0.1

- Publish SMPLwise Dry Contact with HACS metadata, brand icons, English/Hebrew UI and GitHub validation.
