# Third-party dependencies and licenses

SynMachine's original software and accompanying documentation use Apache-2.0.
That grant does not replace the licenses of upstream packages, frameworks or
build tools. Dependencies are downloaded during installation/build and are not
relicensed as SynMachine code.

This inventory records the installed/locked development snapshot inspected on
2026-10-20. It is not a promise that future dependency resolutions use the same
versions: Python and some firmware build dependencies are not fully locked.
Keep upstream license/copyright notices when redistributing their material.
Review notices and source/relinking obligations separately before distributing
compiled firmware, bundled dependencies or packaged applications.

## UI dependency snapshot

Source: `ui/package-lock.json`, including development tools and optional
platform packages. All 76 non-root entries declare a license. Some entries are
platform-specific variants of the same package.

| Package | Version | Declared license |
| --- | --- | --- |
| `@emnapi/core` | 1.11.1 | MIT |
| `@emnapi/runtime` | 1.11.1 | MIT |
| `@emnapi/wasi-threads` | 1.2.2 | MIT |
| `@napi-rs/wasm-runtime` | 1.1.6 | MIT |
| `@oxc-project/types` | 0.137.0 | MIT |
| `@oxlint/binding-android-arm-eabi` | 1.71.0 | MIT |
| `@oxlint/binding-android-arm64` | 1.71.0 | MIT |
| `@oxlint/binding-darwin-arm64` | 1.71.0 | MIT |
| `@oxlint/binding-darwin-x64` | 1.71.0 | MIT |
| `@oxlint/binding-freebsd-x64` | 1.71.0 | MIT |
| `@oxlint/binding-linux-arm-gnueabihf` | 1.71.0 | MIT |
| `@oxlint/binding-linux-arm-musleabihf` | 1.71.0 | MIT |
| `@oxlint/binding-linux-arm64-gnu` | 1.71.0 | MIT |
| `@oxlint/binding-linux-arm64-musl` | 1.71.0 | MIT |
| `@oxlint/binding-linux-ppc64-gnu` | 1.71.0 | MIT |
| `@oxlint/binding-linux-riscv64-gnu` | 1.71.0 | MIT |
| `@oxlint/binding-linux-riscv64-musl` | 1.71.0 | MIT |
| `@oxlint/binding-linux-s390x-gnu` | 1.71.0 | MIT |
| `@oxlint/binding-linux-x64-gnu` | 1.71.0 | MIT |
| `@oxlint/binding-linux-x64-musl` | 1.71.0 | MIT |
| `@oxlint/binding-openharmony-arm64` | 1.71.0 | MIT |
| `@oxlint/binding-win32-arm64-msvc` | 1.71.0 | MIT |
| `@oxlint/binding-win32-ia32-msvc` | 1.71.0 | MIT |
| `@oxlint/binding-win32-x64-msvc` | 1.71.0 | MIT |
| `@rolldown/binding-android-arm64` | 1.1.3 | MIT |
| `@rolldown/binding-darwin-arm64` | 1.1.3 | MIT |
| `@rolldown/binding-darwin-x64` | 1.1.3 | MIT |
| `@rolldown/binding-freebsd-x64` | 1.1.3 | MIT |
| `@rolldown/binding-linux-arm-gnueabihf` | 1.1.3 | MIT |
| `@rolldown/binding-linux-arm64-gnu` | 1.1.3 | MIT |
| `@rolldown/binding-linux-arm64-musl` | 1.1.3 | MIT |
| `@rolldown/binding-linux-ppc64-gnu` | 1.1.3 | MIT |
| `@rolldown/binding-linux-s390x-gnu` | 1.1.3 | MIT |
| `@rolldown/binding-linux-x64-gnu` | 1.1.3 | MIT |
| `@rolldown/binding-linux-x64-musl` | 1.1.3 | MIT |
| `@rolldown/binding-openharmony-arm64` | 1.1.3 | MIT |
| `@rolldown/binding-wasm32-wasi` | 1.1.3 | MIT |
| `@rolldown/binding-win32-arm64-msvc` | 1.1.3 | MIT |
| `@rolldown/binding-win32-x64-msvc` | 1.1.3 | MIT |
| `@rolldown/pluginutils` | 1.0.1 | MIT |
| `@tybys/wasm-util` | 0.10.3 | MIT |
| `@types/node` | 24.13.2 | MIT |
| `@types/react` | 19.2.17 | MIT |
| `@types/react-dom` | 19.2.3 | MIT |
| `@vitejs/plugin-react` | 6.0.3 | MIT |
| `csstype` | 3.2.3 | MIT |
| `detect-libc` | 2.1.2 | Apache-2.0 |
| `fdir` | 6.5.0 | MIT |
| `fsevents` | 2.3.3 | MIT |
| `lightningcss` | 1.32.0 | MPL-2.0 |
| `lightningcss-android-arm64` | 1.32.0 | MPL-2.0 |
| `lightningcss-darwin-arm64` | 1.32.0 | MPL-2.0 |
| `lightningcss-darwin-x64` | 1.32.0 | MPL-2.0 |
| `lightningcss-freebsd-x64` | 1.32.0 | MPL-2.0 |
| `lightningcss-linux-arm-gnueabihf` | 1.32.0 | MPL-2.0 |
| `lightningcss-linux-arm64-gnu` | 1.32.0 | MPL-2.0 |
| `lightningcss-linux-arm64-musl` | 1.32.0 | MPL-2.0 |
| `lightningcss-linux-x64-gnu` | 1.32.0 | MPL-2.0 |
| `lightningcss-linux-x64-musl` | 1.32.0 | MPL-2.0 |
| `lightningcss-win32-arm64-msvc` | 1.32.0 | MPL-2.0 |
| `lightningcss-win32-x64-msvc` | 1.32.0 | MPL-2.0 |
| `nanoid` | 3.3.15 | MIT |
| `oxlint` | 1.71.0 | MIT |
| `picocolors` | 1.1.1 | ISC |
| `picomatch` | 4.0.4 | MIT |
| `postcss` | 8.5.15 | MIT |
| `react` | 19.2.7 | MIT |
| `react-dom` | 19.2.7 | MIT |
| `rolldown` | 1.1.3 | MIT |
| `scheduler` | 0.27.0 | MIT |
| `source-map-js` | 1.2.1 | BSD-3-Clause |
| `tinyglobby` | 0.2.17 | MIT |
| `tslib` | 2.8.1 | 0BSD |
| `typescript` | 6.0.3 | Apache-2.0 |
| `undici-types` | 7.18.2 | MIT |
| `vite` | 8.1.0 | MIT |

## Backend dependency snapshot

Source: installed distribution metadata from the existing development virtual
environment, walking active requirements of the runtime and development roots.
Optional extras for other platforms/configurations are outside this snapshot.

| Package | Version | Declared license |
| --- | --- | --- |
| `annotated-doc` | 0.0.4 | MIT |
| `annotated-types` | 0.7.0 | MIT License |
| `anyio` | 4.14.2 | MIT |
| `click` | 8.4.2 | BSD-3-Clause |
| `dynamixel-sdk` | 3.8.4 | Apache 2.0 |
| `fastapi` | 0.139.2 | MIT |
| `h11` | 0.16.0 | MIT |
| `idna` | 3.18 | BSD-3-Clause |
| `iniconfig` | 2.3.0 | MIT |
| `packaging` | 26.2 | Apache-2.0 OR BSD-2-Clause |
| `pluggy` | 1.6.0 | MIT |
| `pydantic` | 2.13.4 | MIT |
| `pydantic_core` | 2.46.4 | MIT |
| `Pygments` | 2.20.0 | BSD-2-Clause |
| `pyserial` | 3.5 | BSD |
| `pytest` | 9.1.1 | MIT |
| `ruff` | 0.15.22 | MIT |
| `starlette` | 1.3.1 | BSD-3-Clause |
| `typing-inspection` | 0.4.2 | MIT |
| `typing_extensions` | 4.16.0 | PSF-2.0 |
| `uvicorn` | 0.51.0 | BSD-3-Clause |

`pyserial` reports BSD; `annotated-types` reports MIT through its license
classifier. The package's own license text remains authoritative.

## Firmware dependencies and tools

| Component | Inspected version | License/source evidence |
| --- | --- | --- |
| ArduinoJson | 6.21.6 | MIT; installed `LICENSE.txt` |
| Arduino AVR framework | PlatformIO package 5.4.0 | LGPL-2.1-or-later; package metadata and Arduino core headers |
| AVR GCC toolchain | PlatformIO package 1.70300.191015 | Package metadata reports GPL-2.0-or-later; toolchain/runtime components have their own terms and exceptions |

Arduino core and toolchain code retain their upstream terms. Apache-2.0 applies
to original SynMachine firmware source, not to the complete contents of an
Arduino-linked binary. This publication checkpoint creates no firmware binary
release or dependency bundle.

Upstream references:

- [ArduinoJson](https://github.com/bblanchon/ArduinoJson)
- [Arduino AVR core](https://github.com/arduino/ArduinoCore-avr)
- [Arduino core license header](https://github.com/arduino/ArduinoCore-avr/blob/master/cores/arduino/wiring.c)
- [Dynamixel SDK](https://github.com/ROBOTIS-GIT/DynamixelSDK)

Historical project artifacts and any separately attributed material must also
be assessed on their own provenance; an absence of license headers is not proof
of ownership. The current publication decision is recorded in
[PUBLICATION.md](PUBLICATION.md).
