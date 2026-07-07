import { useState } from "react";
import "./App.css";

type Phase =
  | "idle"
  | "b1_to_p1"
  | "p1_to_r"
  | "p1_to_w"
  | "r_to_p2"
  | "p2_to_sf"
  | "sf_to_p2"
  | "p2_to_column";

const phases = {
  idle: {
    title: "IDLE",
    subtitle: "System ready",
    activePath: [] as string[],
    color: "#74839c",
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
    subtitle: "P1 → R",
    activePath: ["P1", "V1", "V2", "R"],
    color: "#46a0ff",
    p1: 0.4,
    p2: 0,
    log: "P1 dispensing into reactor.",
  },
  p1_to_w: {
    title: "DISPENSING",
    subtitle: "P1 → W",
    activePath: ["P1", "V1", "V2", "W"],
    color: "#48d7ff",
    p1: 0.4,
    p2: 0,
    log: "P1 priming / washing to waste.",
  },
  r_to_p2: {
    title: "ASPIRATING",
    subtitle: "R_OUT → P2",
    activePath: ["R", "V3", "P2"],
    color: "#b06cff",
    p1: 0,
    p2: 4.0,
    log: "P2 aspirating reactor mixture.",
  },
  p2_to_sf: {
    title: "DISPENSING",
    subtitle: "P2 → SF_TOP_IN",
    activePath: ["P2", "V3", "V7", "SF"],
    color: "#b06cff",
    p1: 0,
    p2: 1.5,
    log: "P2 dispensing into separatory funnel top inlet.",
  },
  sf_to_p2: {
    title: "ASPIRATING",
    subtitle: "SF_BOTTOM_OUT → P2",
    activePath: ["SF", "V8", "V7", "V3", "P2"],
    color: "#ffb347",
    p1: 0,
    p2: 3.0,
    log: "P2 aspirating lower phase from separatory funnel.",
  },
  p2_to_column: {
    title: "DISPENSING",
    subtitle: "P2 → COLUMN_IN",
    activePath: ["P2", "V3", "V7", "V8", "COLUMN"],
    color: "#ffb347",
    p1: 0,
    p2: 0.8,
    log: "P2 dispensing to column inlet.",
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

function CircleNode({
  id,
  x,
  y,
  className = "",
}: {
  id: string;
  x: number;
  y: number;
  className?: string;
}) {
  return (
    <g>
      <circle cx={x} cy={y} r="24" className={`node ${className}`} />
      <text x={x} y={y + 5} textAnchor="middle" className="nodeText darkText">
        {id}
      </text>
    </g>
  );
}

function RectNode({
  id,
  x,
  y,
  width,
  height,
  rx = 14,
  className = "",
}: {
  id: string;
  x: number;
  y: number;
  width: number;
  height: number;
  rx?: number;
  className?: string;
}) {
  return (
    <g>
      <rect
        x={x - width / 2}
        y={y - height / 2}
        width={width}
        height={height}
        rx={rx}
        className={`node ${className}`}
      />
      <text x={x} y={y + 5} textAnchor="middle" className="nodeText darkText">
        {id}
      </text>
    </g>
  );
}

function VesselNode({
  id,
  x,
  y,
  className = "",
}: {
  id: string;
  x: number;
  y: number;
  className?: string;
}) {
  return (
    <g>
      <rect x={x - 48} y={y - 56} width="96" height="112" rx="22" className={`node ${className}`} />
      <text x={x} y={y + 5} textAnchor="middle" className="nodeText darkText">
        {id}
      </text>
    </g>
  );
}

function ColumnNode({
  x,
  y,
}: {
  x: number;
  y: number;
}) {
  return (
    <g>
      <rect x={x - 26} y={y - 82} width="52" height="164" rx="20" className="node columnNode" />
      <text x={x} y={y + 5} textAnchor="middle" className="nodeText darkText smallText">
        COL
      </text>
    </g>
  );
}

function SmallLabel({
  x,
  y,
  text,
}: {
  x: number;
  y: number;
  text: string;
}) {
  return (
    <text x={x} y={y} className="smallLabel">
      {text}
    </text>
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
        <span>{volume.toFixed(1)} / {max.toFixed(1)} ml</span>
      </div>
      <div className="syringeBar">
        <div className="syringeFill" style={{ width: `${fill}%`, background: color }} />
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
          <div className="subBrand">replica of P1 + reactor + P2 branch</div>
        </div>

        <div className="statusCluster">
          <span className="statusDot" />
          <span>{data.title}</span>
        </div>
      </header>

      <section className="diagramPanel fullWidthPanel">
        <div className="panelTitle">
          <span>Fluid routing diagram</span>
          <span className="pathText">{data.subtitle}</span>
        </div>

        <svg className="labDiagram largeDiagram" viewBox="0 0 1500 680">
          {/* P1 branch sources */}
          <Pipe x1={110} y1={130} x2={240} y2={180} active={edgeActive(data.activePath, "B1", "V4")} color={data.color} />
          <Pipe x1={110} y1={220} x2={240} y2={180} active={edgeActive(data.activePath, "S1", "V4")} color={data.color} />

          <Pipe x1={110} y1={390} x2={240} y2={390} active={edgeActive(data.activePath, "B2", "V5")} color={data.color} />
          <Pipe x1={110} y1={480} x2={240} y2={390} active={edgeActive(data.activePath, "S2", "V5")} color={data.color} />

          <Pipe x1={240} y1={180} x2={390} y2={285} active={edgeActive(data.activePath, "V4", "V6")} color={data.color} />
          <Pipe x1={240} y1={390} x2={390} y2={285} active={edgeActive(data.activePath, "V5", "V6")} color={data.color} />
          <Pipe x1={390} y1={285} x2={545} y2={285} active={edgeActive(data.activePath, "V6", "V1")} color={data.color} />
          <Pipe x1={545} y1={285} x2={700} y2={285} active={edgeActive(data.activePath, "V1", "P1") || edgeActive(data.activePath, "P1", "V1")} color={data.color} />

          {/* V1 down to V2 */}
          <Pipe x1={545} y1={285} x2={545} y2={420} active={edgeActive(data.activePath, "V1", "V2")} color={data.color} />

          {/* V2 to W and reactor */}
          <Pipe x1={545} y1={420} x2={720} y2={420} active={edgeActive(data.activePath, "V2", "W")} color={data.color} />
          <Pipe x1={545} y1={420} x2={890} y2={420} active={edgeActive(data.activePath, "V2", "R")} color={data.color} />

          {/* Reactor to P2 via V3 */}
          <Pipe x1={940} y1={420} x2={1070} y2={420} active={edgeActive(data.activePath, "R", "V3")} color={data.color} />
          <Pipe x1={1070} y1={420} x2={1225} y2={420} active={edgeActive(data.activePath, "V3", "P2") || edgeActive(data.activePath, "P2", "V3")} color={data.color} />

          {/* V3 to V7 */}
          <Pipe x1={1070} y1={420} x2={1070} y2={240} active={edgeActive(data.activePath, "V3", "V7")} color={data.color} />

          {/* V7 to SF top */}
          <Pipe x1={1070} y1={240} x2={1250} y2={240} active={edgeActive(data.activePath, "V7", "SF")} color={data.color} />
          <Pipe x1={1250} y1={240} x2={1325} y2={240} active={edgeActive(data.activePath, "V7", "SF")} color={data.color} />
          <Pipe x1={1325} y1={240} x2={1325} y2={150} active={edgeActive(data.activePath, "V7", "SF")} color={data.color} />

          {/* V7 to V8 */}
          <Pipe x1={1070} y1={240} x2={1200} y2={240} active={edgeActive(data.activePath, "V7", "V8")} color={data.color} />

          {/* SF bottom to V8 */}
          <Pipe x1={1325} y1={285} x2={1325} y2={360} active={edgeActive(data.activePath, "SF", "V8")} color={data.color} />
          <Pipe x1={1325} y1={360} x2={1200} y2={360} active={edgeActive(data.activePath, "SF", "V8")} color={data.color} />
          <Pipe x1={1200} y1={360} x2={1200} y2={240} active={edgeActive(data.activePath, "SF", "V8")} color={data.color} />

          {/* V8 to column */}
          <Pipe x1={1200} y1={240} x2={1400} y2={240} active={edgeActive(data.activePath, "V8", "COLUMN")} color={data.color} />
          <Pipe x1={1400} y1={240} x2={1400} y2={420} active={edgeActive(data.activePath, "V8", "COLUMN")} color={data.color} />

          {/* Nodes */}
          <CircleNode id="B1" x={85} y={130} className="bottleB1" />
          <CircleNode id="S1" x={85} y={220} className="bottleS1" />
          <CircleNode id="B2" x={85} y={390} className="bottleB2" />
          <CircleNode id="S2" x={85} y={480} className="bottleS2" />

          <CircleNode id="V4" x={240} y={180} className="valveNode" />
          <CircleNode id="V5" x={240} y={390} className="valveNode" />
          <CircleNode id="V6" x={390} y={285} className="valveNode" />
          <CircleNode id="V1" x={545} y={285} className="valveNode" />
          <RectNode id="P1" x={700} y={285} width={92} height={56} className="pumpNode" />
          <CircleNode id="V2" x={545} y={420} className="valveNode" />
          <CircleNode id="W" x={720} y={420} className="wasteNode" />
          <VesselNode id="R" x={890} y={420} className="reactorNode" />

          <CircleNode id="V3" x={1070} y={420} className="valveNode" />
          <RectNode id="P2" x={1225} y={420} width={92} height={56} className="pumpNode" />
          <CircleNode id="V7" x={1070} y={240} className="valveNode" />
          <CircleNode id="V8" x={1200} y={240} className="valveNode" />
          <VesselNode id="SF" x={1325} y={220} className="sfNode" />
          <ColumnNode x={1400} y={420} />

          {/* Labels */}
          <SmallLabel x={1272} y={132} text="SF_TOP_IN" />
          <SmallLabel x={1260} y={332} text="SF_BOTTOM_OUT" />
          <SmallLabel x={1360} y={225} text="COLUMN_IN" />
          <SmallLabel x={845} y={392} text="R_IN / R_OUT through reactor body" />
        </svg>
      </section>

      <section className="controlsPanel fullWidthPanel">
        <div className="panelTitle">
          <span>Controls</span>
          <span className="pathText">full-width command area</span>
        </div>

        <div className="controlsTop">
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

          <PumpWidget label="P1 syringe" volume={data.p1} max={5} color={data.color} />
          <PumpWidget label="P2 syringe" volume={data.p2} max={10} color={data.color} />
        </div>

        <div className="buttonRow">
          <PhaseButton label="Idle" active={phase === "idle"} onClick={() => setPhase("idle")} />
          <PhaseButton label="B1 → P1" active={phase === "b1_to_p1"} onClick={() => setPhase("b1_to_p1")} />
          <PhaseButton label="P1 → R" active={phase === "p1_to_r"} onClick={() => setPhase("p1_to_r")} />
          <PhaseButton label="P1 → W" active={phase === "p1_to_w"} onClick={() => setPhase("p1_to_w")} />
          <PhaseButton label="R → P2" active={phase === "r_to_p2"} onClick={() => setPhase("r_to_p2")} />
          <PhaseButton label="P2 → SF" active={phase === "p2_to_sf"} onClick={() => setPhase("p2_to_sf")} />
          <PhaseButton label="SF → P2" active={phase === "sf_to_p2"} onClick={() => setPhase("sf_to_p2")} />
          <PhaseButton label="P2 → Column" active={phase === "p2_to_column"} onClick={() => setPhase("p2_to_column")} />
        </div>
      </section>

      <section className="bottomConsole">
        <div className="protocolPanel">
          <div className="panelTitle">Protocol steps</div>
          <ol>
            <li className={phase === "b1_to_p1" || phase === "p1_to_r" ? "running" : ""}>
              B1 / S1 / B2 / S2 → P1 → R
            </li>
            <li className={phase === "p1_to_w" ? "running" : ""}>
              P1 priming / wash → W
            </li>
            <li className={phase === "r_to_p2" || phase === "p2_to_sf" ? "running" : ""}>
              R_OUT → P2 → SF_TOP_IN
            </li>
            <li className={phase === "sf_to_p2" || phase === "p2_to_column" ? "running" : ""}>
              SF_BOTTOM_OUT → P2 → COLUMN_IN
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
