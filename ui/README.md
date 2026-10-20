# SynMachine UI

The React, TypeScript and Vite interface provides the schematic, Guided Demo,
Recipes / Procedure Builder, execution status and supervised Service controls.

See the [project README](../README.md) for the prototype scope and fake-device
quick start, and the [recipe guide](docs/UVP_USER_GUIDE.md) for procedure editing.

```bash
npm ci
npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

The development proxy expects the backend on localhost:8000. Opening the UI does
not itself authorize execution. Connection labels distinguish real, fake and
unidentified device environments.

```bash
npm test
npm run lint
npm run build
```

Current canonical state is in [../docs/LABFORGE_CURRENT_STATE.md](../docs/LABFORGE_CURRENT_STATE.md).
The package remains named `labforge-ui`; this is an internal compatibility name.
