import "./App.css";

type ValveState = "closed" | "k1k3" | "k1k2";

function Pipe({ d, active = false }: { d: string; active?: boolean }) {
  return <path d={d} className={active ? "pipe activePipe" : "pipe"} />;
}

function Valve({
  id,
  x,
  y,
  state = "closed",
}: {
  id: string;
  x: number;
  y: number;
  state?: ValveState;
}) {
  const activeK1 = state === "k1k3" || state === "k1k2";
  const activeK2 = state === "k1k2";
  const activeK3 = state === "k1k3";

  return (
    <g transform={`translate(${x} ${y}) scale(0.62)`}>
      {/* port stubs: k1 right, k2 left, k3 top */}
      <line x1={58} y1={0} x2={105} y2={0} className="valveStub" />
      <line x1={-58} y1={0} x2={-105} y2={0} className="valveStub" />
      <line x1={0} y1={-58} x2={0} y2={-105} className="valveStub" />

      {activeK1 && (
        <line x1={58} y1={0} x2={105} y2={0} className="valveStubActive" />
      )}
      {activeK2 && (
        <line x1={-58} y1={0} x2={-105} y2={0} className="valveStubActive" />
      )}
      {activeK3 && (
        <line x1={0} y1={-58} x2={0} y2={-105} className="valveStubActive" />
      )}

      <rect
        x={91}
        y={-14}
        width={28}
        height={28}
        rx={7}
        className={activeK1 ? "collar activeCollar" : "collar"}
      />
      <rect
        x={-119}
        y={-14}
        width={28}
        height={28}
        rx={7}
        className={activeK2 ? "collar activeCollar" : "collar"}
      />
      <rect
        x={-14}
        y={-119}
        width={28}
        height={28}
        rx={7}
        className={activeK3 ? "collar activeCollar" : "collar"}
      />

      <path
        d="M -72 -48 Q -72 -66 -54 -75 L 54 -75 Q 72 -66 72 -48 L 72 48 Q 72 66 54 75 L -54 75 Q -72 66 -72 48 Z"
        className="valveShadow"
        transform="translate(5 7)"
      />
      <path
        d="M -72 -48 Q -72 -66 -54 -75 L 54 -75 Q 72 -66 72 -48 L 72 48 Q 72 66 54 75 L -54 75 Q -72 66 -72 48 Z"
        className="valveBody"
      />

      <circle cx={0} cy={0} r={45} className="rotorPlate" />
      <circle cx={0} cy={0} r={31} className="rotorInner" />

      {state === "closed" && (
        <>
          <line x1={-22} y1={22} x2={22} y2={-22} className="closedMark" />
          <line x1={-22} y1={-22} x2={22} y2={22} className="closedMark" />
          <circle cx={0} cy={0} r={6} className="hubDot closedDot" />
        </>
      )}

      {state === "k1k2" && (
        <>
          <line x1={-50} y1={0} x2={50} y2={0} className="internalPath" />
          <circle cx={0} cy={0} r={7} className="hubDot activeDot" />
        </>
      )}

      {state === "k1k3" && (
        <>
          <path d="M 0 -50 L 0 0 L 50 0" className="internalPath" />
          <circle cx={0} cy={0} r={7} className="hubDot activeDot" />
        </>
      )}

      <circle cx={-48} cy={-50} r={4} className="bolt" />
      <circle cx={48} cy={-50} r={4} className="bolt" />
      <circle cx={-48} cy={50} r={4} className="bolt" />
      <circle cx={48} cy={50} r={4} className="bolt" />

      <text x={0} y={9} textAnchor="middle" className="valveLabel">
        {id}
      </text>

      <text x={137} y={8} textAnchor="middle" className="portHint">
        k1
      </text>
      <text x={-137} y={8} textAnchor="middle" className="portHint">
        k2
      </text>
      <text x={0} y={-137} textAnchor="middle" className="portHint">
        k3
      </text>
    </g>
  );
}

function Bottle({
  id,
  x,
  y,
  liquidClass,
}: {
  id: string;
  x: number;
  y: number;
  liquidClass: string;
}) {
  return (
    <g transform={`translate(${x} ${y})`}>
      <rect x={30} y={-7} width={14} height={14} rx={4} className="bottleOutlet" />
      <rect x={-34} y={-46} width={68} height={92} rx={16} className="bottleBody" />
      <rect x={-22} y={-60} width={44} height={18} rx={7} className="bottleNeck" />
      <rect x={-26} y={-12} width={52} height={40} rx={10} className={liquidClass} />
      <path d="M -20 -34 Q -27 -12 -23 13" className="bottleHighlight" />
      <text x={0} y={8} textAnchor="middle" className="nodeLabel">
        {id}
      </text>
    </g>
  );
}

function Pump({ id, x, y }: { id: string; x: number; y: number }) {
  return (
    <g transform={`translate(${x} ${y})`}>
      <rect x={-28} y={-72} width={56} height={144} rx={18} className="pumpBody" />
      <rect x={-12} y={-46} width={24} height={70} rx={8} className="pumpChamber" />
      <line x1={0} y1={24} x2={0} y2={60} className="plunger" />
      <circle cx={0} cy={-48} r={7} className="pumpDot" />
      <text x={0} y={7} textAnchor="middle" className="pumpLabel">
        {id}
      </text>
    </g>
  );
}

function Reactor({ x, y }: { x: number; y: number }) {
  return (
    <g transform={`translate(${x} ${y})`}>
      <rect x={-64} y={-52} width={128} height={104} rx={30} className="reactorBody" />
      <rect x={-40} y={10} width={80} height={26} rx={13} className="reactorLiquid" />
      <text x={0} y={6} textAnchor="middle" className="nodeLabel">
        R
      </text>
    </g>
  );
}

function Separator({ x, y }: { x: number; y: number }) {
  const bodyPath =
    "M -13 -62 C -38 -59 -52 -43 -52 -18 C -52 7 -35 28 -18 45 C -11 52 -8 59 -8 66 L 8 66 C 8 59 11 52 18 45 C 35 28 52 7 52 -18 C 52 -43 38 -59 13 -62 Z";

  return (
    <g transform={`translate(${x} ${y})`}>
      <defs>
        <clipPath id="separatorBodyClip">
          <path d={bodyPath} />
        </clipPath>
      </defs>

      <rect x={-12} y={-90} width={24} height={31} rx={7} className="sfNeck" />
      <rect x={-18} y={-99} width={36} height={12} rx={6} className="sfRim" />
      <ellipse cx={0} cy={-96} rx={12} ry={4} className="sfOpening" />

      <path d={bodyPath} className="sfBody" />
      <g clipPath="url(#separatorBodyClip)">
        <rect x={-54} y={-25} width={108} height={30} className="sfLiquidTop" />
        <rect x={-54} y={5} width={108} height={52} className="sfLiquidBottom" />
      </g>
      <path d={bodyPath} className="sfOutline" />
      <path d="M -31 -43 C -42 -29 -41 -9 -31 7" className="sfGlassHighlight" />

      <rect x={-7} y={63} width={14} height={26} rx={4} className="sfStem" />
      <rect x={-22} y={78} width={44} height={12} rx={6} className="sfStopcock" />
      <circle cx={0} cy={84} r={7} className="sfStopcockHub" />
      <rect x={-5} y={88} width={10} height={17} rx={3} className="sfStem" />

      <text x={0} y={-2} textAnchor="middle" className="nodeLabel">
        SF
      </text>
    </g>
  );
}

function Column({ x, y }: { x: number; y: number }) {
  return (
    <g transform={`translate(${x} ${y})`}>
      <rect x={-24} y={-82} width={48} height={164} rx={18} className="columnBody" />
      <rect x={-17} y={-42} width={34} height={88} rx={14} className="columnPacking" />
      <text x={0} y={8} textAnchor="middle" className="smallDarkLabel">
        COL
      </text>
    </g>
  );
}

function Waste({ x, y }: { x: number; y: number }) {
  return (
    <g transform={`translate(${x} ${y})`}>
      <path d="M -42 -30 L 42 -30 L 30 46 L -30 46 Z" className="wasteBody" />
      <text x={0} y={10} textAnchor="middle" className="nodeLabel">
        W
      </text>
    </g>
  );
}

function Fractions({ x, y }: { x: number; y: number }) {
  return (
    <g transform={`translate(${x} ${y})`}>
      <rect x={-70} y={32} width={140} height={16} rx={6} className="rack" />
      {[-45, -15, 15, 45].map((tx) => (
        <rect key={tx} x={tx - 10} y={-36} width={20} height={70} rx={8} className="tube" />
      ))}
      <text x={0} y={72} textAnchor="middle" className="externalLabel">
        Fractions
      </text>
    </g>
  );
}

export default function App() {
  return (
    <main className="appShell">
      <header className="topBar">
        <div>
          <div className="brand">LABFORGE SCHEME DRAFT</div>
          <div className="subBrand">
            Ventil verzija 2, portovi označeni, aktivna ruta: B1 → P1
          </div>
        </div>

        <div className="statusPill">SCHEME PREVIEW</div>
      </header>

      <section className="workspaceGrid">
        <aside className="sidePanel leftPanel" aria-label="Protocol status">
          <div className="panelBlock">
            <div className="panelEyebrow">Protocol</div>
            <div className="panelValue">Colored water demo</div>
          </div>

          <div className="metricGrid">
            <div className="metricTile">
              <span>Step</span>
              <strong>1 / 5</strong>
            </div>
            <div className="metricTile">
              <span>Volume</span>
              <strong>2.0 ml</strong>
            </div>
          </div>

          <div className="panelBlock">
            <div className="panelEyebrow">Current action</div>
            <div className="actionText">Transfer B1 to Reactor</div>
          </div>

          <div className="controlRow" aria-label="Run controls">
            <button className="controlButton runButton" type="button">
              Run
            </button>
            <button className="controlButton" type="button">
              Pause
            </button>
            <button className="controlButton abortButton" type="button">
              Abort
            </button>
          </div>
        </aside>

        <section className="schemePanel" aria-label="Physical scheme">
          <svg className="schemeCanvas" viewBox="-900 -420 1800 840">
          {/* P1 input pipes */}
          <Pipe d="M -716 -210 L -665 -210" active />
          <Pipe d="M -716 -335 L -600 -335 L -600 -275" />
          <Pipe d="M -535 -210 L -455 -210 L -390 -95" active />

          <Pipe d="M -716 150 L -665 150" />
          <Pipe d="M -716 15 L -600 15 L -600 85" />
          <Pipe d="M -535 150 L -500 150 L -500 -30 L -455 -30" />

          <Pipe d="M -325 -30 L -300 -30 L -300 -120 L -170 -120 L -170 -95" active />
          <Pipe d="M -105 -30 L 2 -30" active />

          {/* P1 output / reactor / waste pipes */}
          <Pipe d="M -235 -30 L -280 -30 L -280 235 L -105 235 L -105 165" />
          <Pipe d="M -170 100 L 185 100 L 185 165 L 206 165" />
          <Pipe d="M -235 165 L -320 165 L -320 270 L -170 270" />

          {/* P2 branch pipes */}
          <Pipe d="M 335 165 L 370 165 L 370 100 L 470 100" />
          <Pipe d="M 535 165 L 632 165" />
          <Pipe d="M 405 165 L 380 165 L 380 65 L 560 65 L 560 0 L 535 0" />
          <Pipe d="M 405 0 L 340 0 L 340 -340 L 650 -340 L 650 -309" />
          <Pipe d="M 470 -65 L 470 -90 L 750 -90 L 750 0 L 715 0" />
          <Pipe d="M 585 0 L 550 0 L 550 -120 L 650 -120 L 650 -105" />
          <Pipe d="M 650 -65 L 720 -65 L 720 65 L 800 65 L 800 83" />
          <Pipe d="M 800 247 L 800 270 L 840 270" />

          {/* P1 branch nodes */}
          <Bottle id="B1" x={-760} y={-210} liquidClass="liquidBlue" />
          <Bottle id="S1" x={-760} y={-335} liquidClass="liquidCyan" />
          <Valve id="V4" x={-600} y={-210} state="k1k2" />

          <Bottle id="B2" x={-760} y={150} liquidClass="liquidPurple" />
          <Bottle id="S2" x={-760} y={15} liquidClass="liquidGreen" />
          <Valve id="V5" x={-600} y={150} state="closed" />

          <Valve id="V6" x={-390} y={-30} state="k1k3" />
          <Valve id="V1" x={-170} y={-30} state="k1k3" />
          <Pump id="P1" x={30} y={-30} />

          <Valve id="V2" x={-170} y={165} state="closed" />
          <Waste x={-170} y={300} />
          <Reactor x={270} y={165} />

          {/* P2 branch nodes */}
          <Valve id="V3" x={470} y={165} state="closed" />
          <Pump id="P2" x={660} y={165} />
          <Valve id="V7" x={470} y={0} state="closed" />
          <Separator x={650} y={-210} />
          <Valve id="V8" x={650} y={0} state="closed" />
          <Column x={800} y={165} />
          <Fractions x={840} y={295} />

          <text x={-700} y={-350} className="sectionLabel">
            P1 input / reactor loading
          </text>
          <text x={410} y={-380} className="sectionLabel">
            P2 output / SF / column
          </text>
          </svg>
        </section>

        <aside className="sidePanel rightPanel" aria-label="Hardware status">
          <div className="panelBlock">
            <div className="panelEyebrow">Hardware status</div>
            <div className="statusList">
              <div>
                <span>P1</span>
                <strong>Ready</strong>
              </div>
              <div>
                <span>P2</span>
                <strong>Idle</strong>
              </div>
              <div>
                <span>Reactor</span>
                <strong>Receiving</strong>
              </div>
              <div>
                <span>Separator</span>
                <strong>Standby</strong>
              </div>
              <div>
                <span>Column</span>
                <strong>Not loaded</strong>
              </div>
            </div>
          </div>

          <div className="alertBox">
            <span>Alerts</span>
            <strong>No active alerts</strong>
          </div>
        </aside>
      </section>

      <section className="bottomBar" aria-label="Command and telemetry">
        <input className="commandInput" type="text" placeholder="Type command..." />
        <div className="telemetryLog">
          <div>12:04 Route preview ready: B1 to Reactor.</div>
          <div>12:05 V4 and V6 aligned for aspirate phase.</div>
          <div>12:05 P1 ready for 2.0 ml transfer.</div>
        </div>
      </section>
    </main>
  );
}
