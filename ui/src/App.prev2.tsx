import { useState } from "react";
import "./App.css";

type Phase =
  | "idle"
  | "b1_to_p1"
  | "p1_to_r"
  | "r_to_p2"
  | "p2_to_sf"
  | "sf_to_column";

const phases = {
  idle: {
    title: "IDLE",
    subtitle: "System ready",
    activePath: [] as string[],
    color: "#7c8aa5",
    p1: 0,
    p2: 0,
    log: "System idle. Waiting for command.",
  },
  b1_to_p1: {
    title: "ASPIRATING",
    subtitle: "B1 → P1",
    activePath: ["B1", "V4", "V6", "V1", "P1"],
    color: "#46a0ff",
    p1: 2.0,
    p2: 0,
    log: "P1 aspirating 2.0 ml from B1.",
  },
  p1_to_r: {
    title: "DISPENSING",
    subtitle: "P1 → Reactor",
    activePath: ["P1", "V1", "V2", "R"],
    color: "#46a0ff",
    p1: 0.5,
    p2: 0,
    log: "P1 dispensing B1 into reactor.",
  },
  r_to_p2: {
    title: "ASPIRATING",
    subtitle: "Reactor → P2",
    activePath: ["R", "V3", "P2"],
    color: "#b06cff",
    p1: 0,
    p2: 4.0,
    log: "P2 aspirating reactor mixture.",
  },
  p2_to_sf: {
    title: "DISPENSING",
    subtitle: "P2 → SF",
    activePath: ["P2", "V3", "V7", "SF"],
    color: "#b06cff",
    p1: 0,
    p2: 1.5,
    log: "P2 dispensing mixture into separatory funnel.",
  },
  sf_to_column: {
    title: "TRANSFER",
    subtitle: "SF → Column",
    activePath: ["SF", "V8", "COLUMN"],
    color: "#ffb347",
    p1: 0,
    p2: 0,
    log: "Bottom phase routed toward column.",
  },
};

function edgeActive(path: string[], a: string, b: string) {
  const ia = path.indexOf(a);
  const ib = path.indexOf(b);
  return ia !== -1 && ib !== -1 && Math.abs(ia - ib) === 1;
}

function Pipe({
  x1,
  y1,
  x2,
  y2,
  active,
  color,
}: {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  active: boolean;
  color: string;
}) {
  return (
    <g>
      <line className="pipeBase" x1={x1} y1={y1} x2={x2} y2={y2} />
      {active && (
        <line
          className="pipeFlow"
          style={{ stroke: color }}
          x1={x1}
          y1={y1}
          x2={x2}
          y2={y2}
        />
      )}
    </g>
  );
}

function Node({
  id,
  x,
  y,
  kind = "round",
  extraClass = "",
}: {
  id: string;
  x: number;
  y: number;
  kind?: "round" | "pump" | "reactor" | "column";
  extraClass?: string;
}) {
  if (kind === "pump") {
    return (
      <g>
        <rect
          x={x - 38}
          y={y - 22}
          width="76"
          height="44"
          rx="12"
          className={`node pumpNode ${extraClass}`}
        />
        <text x={x} y={y + 5} textAnchor="middle" className="nodeText">
          {id}
        </text>
      </g>
    );
  }

  if (kind === "reactor") {
    return (
      <g>
        <rect
          x={x - 42}
          y={y - 48}
          width="84"
          height="96"
          rx="18"
          className={`node reactorNode ${extraClass}`}
        />
        <text x={x} y={y + 5} textAnchor="middle" className="nodeText">
          {id}
        </text>
      </g>
    );
  }

  if (kind === "column") {
    return (
      <g>
        <rect
          x={x - 22}
          y={y - 66}
          width="44"
          height="132"
          rx="18"
          className={`node columnNode ${extraClass}`}
        />
        <text x={x} y={y + 5} textAnchor="middle" className="nodeText small">
          COL
        </text>
      </g>
    );
  }

  return (
    <g>
      <circle cx={x} cy={y} r="23" className={`node ${extraClass}`} />
      <text x={x} y={y + 5} textAnchor="middle" className="nodeText">
        {id}
      </text>
    </g>
  );
}

function PumpWidget({
  label,
  volume,
  max,
  color,
}: {
  label: string;
  volume: number;
  max: number;
  color: string;
}) {
  const fill = Math.max(0, Math.min(100, (volume / max) * 100));

  return (
    <div className="pumpWidget">
      <div className="widgetHeader">
        <span>{label}</span>
        <span>
          {volume.toFixed(1)} / {max.toFixed(1)} ml
        </span>
      </div>
      <div className="syringeBar">
        <div
          className="syringeFill"
          style={{ width: `${fill}%`, background: color }}
        />
      </div>
    </div>
  );
}

function PhaseButton({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button className={`phaseButton ${active ? "active" : ""}`} onClick={onClick}>
      {label}
    </button>
  );
}

export default function App() {
  const [phase, setPhase] = useState<Phase>("idle");
  const data = phases[phase];

  return (
    <main className="appShell">
      <header className="topBar">
        <div>
          <div className="brand">LABFORGE CONSOLE</div>
          <div className="subBrand">experimental chemputer UI mockup</div>
        </div>

        <div className="statusCluster">
          <span className="statusDot" />
          <span>{data.title}</span>
        </div>
      </header>

      <section className="mainGrid">
        <div className="diagramPanel">
          <div className="panelTitle">
            <span>Fluid routing diagram</span>
            <span className="pathText">{data.subtitle}</span>
          </div>

          <svg className="labDiagram" viewBox="0 0 1000 520">
            <Pipe x1={100} y1={120} x2={210} y2={160} active={edgeActive(data.activePath, "B1", "V4")} color={data.color} />
            <Pipe x1={100} y1={220} x2={210} y2={160} active={edgeActive(data.activePath, "S1", "V4")} color={data.color} />

            <Pipe x1={100} y1={330} x2={210} y2={330} active={edgeActive(data.activePath, "B2", "V5")} color={data.color} />
            <Pipe x1={100} y1={430} x2={210} y2={330} active={edgeActive(data.activePath, "S2", "V5")} color={data.color} />

            <Pipe x1={210} y1={160} x2={340} y2={210} active={edgeActive(data.activePath, "V4", "V6")} color={data.color} />
            <Pipe x1={210} y1={330} x2={340} y2={210} active={edgeActive(data.activePath, "V5", "V6")} color={data.color} />
            <Pipe x1={340} y1={210} x2={470} y2={210} active={edgeActive(data.activePath, "V6", "V1")} color={data.color} />
            <Pipe x1={470} y1={210} x2={610} y2={210} active={edgeActive(data.activePath, "V1", "P1") || edgeActive(data.activePath, "P1", "V1")} color={data.color} />
            <Pipe x1={470} y1={210} x2={470} y2={330} active={edgeActive(data.activePath, "V1", "V2")} color={data.color} />
            <Pipe x1={470} y1={330} x2={670} y2={330} active={edgeActive(data.activePath, "V2", "R")} color={data.color} />

            <Pipe x1={712} y1={330} x2={790} y2={330} active={edgeActive(data.activePath, "R", "V3")} color={data.color} />
            <Pipe x1={790} y1={330} x2={890} y2={330} active={edgeActive(data.activePath, "V3", "P2")} color={data.color} />
            <Pipe x1={890} y1={330} x2={890} y2={210} active={edgeActive(data.activePath, "P2", "V3")} color={data.color} />
            <Pipe x1={890} y1={210} x2={760} y2={120} active={edgeActive(data.activePath, "V3", "V7")} color={data.color} />
            <Pipe x1={760} y1={120} x2={640} y2={120} active={edgeActive(data.activePath, "V7", "SF")} color={data.color} />

            <Pipe x1={640} y1={168} x2={780} y2={420} active={edgeActive(data.activePath, "SF", "V8")} color={data.color} />
            <Pipe x1={780} y1={420} x2={930} y2={420} active={edgeActive(data.activePath, "V8", "COLUMN")} color={data.color} />

            <Node id="B1" x={80} y={120} extraClass="bottleB1" />
            <Node id="S1" x={80} y={220} extraClass="bottleS1" />
            <Node id="B2" x={80} y={330} extraClass="bottleB2" />
            <Node id="S2" x={80} y={430} extraClass="bottleS2" />

            <Node id="V4" x={210} y={160} extraClass="valveNode" />
            <Node id="V5" x={210} y={330} extraClass="valveNode" />
            <Node id="V6" x={340} y={210} extraClass="valveNode" />
            <Node id="V1" x={470} y={210} extraClass="valveNode" />
            <Node id="V2" x={470} y={330} extraClass="valveNode" />
            <Node id="V3" x={790} y={330} extraClass="valveNode" />
            <Node id="V7" x={760} y={120} extraClass="valveNode" />
            <Node id="V8" x={780} y={420} extraClass="valveNode" />

            <Node id="P1" x={610} y={210} kind="pump" extraClass="pumpAccent" />
            <Node id="R" x={670} y={330} kind="reactor" extraClass="reactorAccent" />
            <Node id="P2" x={890} y={330} kind="pump" extraClass="pumpAccent" />
            <Node id="SF" x={640} y={120} kind="reactor" extraClass="sfAccent" />
            <Node id="COLUMN" x={930} y={420} kind="column" extraClass="columnAccent" />
          </svg>
        </div>

        <aside className="sidePanel">
          <div className="panelTitle">BIOS-style controls</div>

          <div className="knobGrid">
            <div className="knob">
              <div className="knobCircle">2.0</div>
              <span>Volume ml</span>
            </div>
            <div className="knob">
              <div className="knobCircle">1.0x</div>
              <span>Speed</span>
            </div>
            <div className="knob">
              <div className="knobCircle">5s</div>
              <span>Delay</span>
            </div>
            <div className="knob">
              <div className="knobCircle">SIM</div>
              <span>Mode</span>
            </div>
          </div>

          <PumpWidget label="P1 syringe" volume={data.p1} max={5} color={data.color} />
          <PumpWidget label="P2 syringe" volume={data.p2} max={10} color={data.color} />

          <div className="buttonStack">
            <PhaseButton label="Idle" active={phase === "idle"} onClick={() => setPhase("idle")} />
            <PhaseButton label="B1 → P1" active={phase === "b1_to_p1"} onClick={() => setPhase("b1_to_p1")} />
            <PhaseButton label="P1 → R" active={phase === "p1_to_r"} onClick={() => setPhase("p1_to_r")} />
            <PhaseButton label="R → P2" active={phase === "r_to_p2"} onClick={() => setPhase("r_to_p2")} />
            <PhaseButton label="P2 → SF" active={phase === "p2_to_sf"} onClick={() => setPhase("p2_to_sf")} />
            <PhaseButton label="SF → Column" active={phase === "sf_to_column"} onClick={() => setPhase("sf_to_column")} />
          </div>
        </aside>
      </section>

      <section className="bottomConsole">
        <div className="protocolPanel">
          <div className="panelTitle">Protocol steps</div>
          <ol>
            <li className={phase === "b1_to_p1" || phase === "p1_to_r" ? "running" : ""}>
              Transfer B1 → R, 2.0 ml
            </li>
            <li className={phase === "r_to_p2" || phase === "p2_to_sf" ? "running" : ""}>
              Transfer R_OUT → SF_TOP_IN
            </li>
            <li className={phase === "sf_to_column" ? "running" : ""}>
              Transfer SF_BOTTOM → COLUMN
            </li>
          </ol>
        </div>

        <div className="logPanel">
          <div className="panelTitle">Telemetry log</div>
          <div className="logLine">12:00:01 SYSTEM_READY simulation mode</div>
          <div className="logLine">12:00:02 ACTIVE_PHASE {data.subtitle}</div>
          <div className="logLine">12:00:03 {data.log}</div>
          <div className="commandLine">&gt; transfer B1 R 2</div>
        </div>
      </section>
    </main>
  );
}
