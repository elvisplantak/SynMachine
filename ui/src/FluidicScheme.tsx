import type { FlowDirection, FlowValveState } from "./executionFlow";

type ValveState = "closed" | "unknown" | FlowValveState;
type ValvePort = "k1" | "k2" | "k3";
type ValveStubPosition = "right" | "left" | "top";
type ValvePortMap = Record<ValvePort, ValveStubPosition>;

function Pipe({ d, active = false, direction = "forward", segment }: { d: string; active?: boolean; direction?: FlowDirection; segment: string }) {
  if (!active) {
    return <path d={d} className="pipe" />;
  }

  return (
    <g className="activePipe" data-segment={segment} data-direction={direction}>
      <path d={d} className="pipe activePipeGlow" />
      <path d={d} className={`pipe activePipeFlow${direction === "reverse" ? " reverseFlow" : ""}`} />
    </g>
  );
}

const defaultValvePortMap: ValvePortMap = {
  k1: "right",
  k2: "left",
  k3: "top",
};

const valveStubGeometry: Record<
  ValveStubPosition,
  {
    line: { x1: number; y1: number; x2: number; y2: number };
    collar: { x: number; y: number };
    label: { x: number; y: number };
  }
> = {
  right: {
    line: { x1: 58, y1: 0, x2: 105, y2: 0 },
    collar: { x: 91, y: -14 },
    label: { x: 137, y: 8 },
  },
  left: {
    line: { x1: -58, y1: 0, x2: -105, y2: 0 },
    collar: { x: -119, y: -14 },
    label: { x: -137, y: 8 },
  },
  top: {
    line: { x1: 0, y1: -58, x2: 0, y2: -105 },
    collar: { x: -14, y: -119 },
    label: { x: 0, y: -137 },
  },
};

function getInternalPath(from: ValveStubPosition, to: ValveStubPosition) {
  const key = [from, to].sort().join("-");

  if (key === "left-right") {
    return <line x1={-50} y1={0} x2={50} y2={0} className="internalPath" />;
  }

  if (key === "right-top") {
    return <path d="M 0 -50 L 0 0 L 50 0" className="internalPath" />;
  }

  return <path d="M -50 0 L 0 0 L 0 -50" className="internalPath" />;
}

function Valve({
  id,
  x,
  y,
  state = "closed",
  rotation = 0,
  portMap = defaultValvePortMap,
}: {
  id: string;
  x: number;
  y: number;
  state?: ValveState;
  rotation?: number;
  portMap?: ValvePortMap;
}) {
  const activeK1 = state === "k1k3" || state === "k1k2";
  const activeK2 = state === "k1k2";
  const activeK3 = state === "k1k3";
  const activePorts: ValvePort[] = [
    ...(activeK1 ? (["k1"] as const) : []),
    ...(activeK2 ? (["k2"] as const) : []),
    ...(activeK3 ? (["k3"] as const) : []),
  ];
  const activeStubPositions = activePorts.map((port) => portMap[port]);

  return (
    <g transform={`translate(${x} ${y}) scale(0.62)`}>
      <g transform={`rotate(${rotation})`}>
      {Object.entries(valveStubGeometry).map(([position, geometry]) => (
        <line key={position} {...geometry.line} className="valveStub" />
      ))}

      {activeStubPositions.map((position) => (
        <line key={position} {...valveStubGeometry[position].line} className="valveStubActive" />
      ))}

      {(Object.keys(valveStubGeometry) as ValveStubPosition[]).map((position) => (
        <rect
          key={position}
          x={valveStubGeometry[position].collar.x}
          y={valveStubGeometry[position].collar.y}
          width={28}
          height={28}
          rx={7}
          className={activeStubPositions.includes(position) ? "collar activeCollar" : "collar"}
        />
      ))}

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
          {getInternalPath(portMap.k1, portMap.k2)}
          <circle cx={0} cy={0} r={7} className="hubDot activeDot" />
        </>
      )}

      {state === "k1k3" && (
        <>
          {getInternalPath(portMap.k1, portMap.k3)}
          <circle cx={0} cy={0} r={7} className="hubDot activeDot" />
        </>
      )}

      <circle cx={-48} cy={-50} r={4} className="bolt" />
      <circle cx={48} cy={-50} r={4} className="bolt" />
      <circle cx={-48} cy={50} r={4} className="bolt" />
      <circle cx={48} cy={50} r={4} className="bolt" />

      <text
        x={0}
        y={9}
        textAnchor="middle"
        className="valveLabel"
        transform={`rotate(${-rotation} 0 9)`}
      >
        {id}
      </text>

      {(Object.keys(portMap) as ValvePort[]).map((port) => {
        const label = valveStubGeometry[portMap[port]].label;

        return (
          <text
            key={port}
            x={label.x}
            y={label.y}
            textAnchor="middle"
            className="portHint"
            transform={`rotate(${-rotation} ${label.x} ${label.y})`}
          >
            {port}
          </text>
        );
      })}
      </g>
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

function ColumnBottomValve({ x, y }: { x: number; y: number }) {
  return (
    <g transform={`translate(${x} ${y})`}>
      <line x1={0} y1={-31} x2={0} y2={-16} className="valveStub" />
      <line x1={18} y1={0} x2={42} y2={0} className="valveStub" />
      <rect x={-18} y={-18} width={36} height={36} rx={8} className="collar" />
      <circle cx={0} cy={0} r={11} className="rotorInner" />
      <text x={0} y={7} textAnchor="middle" className="smallDarkLabel">
        BV
      </text>
    </g>
  );
}

function Waste({ x, y }: { x: number; y: number }) {
  return (
    <g transform={`translate(${x} ${y})`}>
      <path d="M -42 -30 L 42 -30 L 30 46 L -30 46 Z" className="wasteBody" />
      <text x={0} y={10} textAnchor="middle" className="wasteLabel">
        WASTE
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

export function FluidicScheme({ activeSegments = new Set(["b1-v4", "v4-v6", "v6-v1", "v1-p1"]), directions, valves }: {
  activeSegments?: Set<string>; directions?: Partial<Record<string, FlowDirection>>;
  valves?: Partial<Record<string, FlowValveState>>;
}) {
  const isActive = (segment: string) => directions ? directions[segment] !== undefined : activeSegments.has(segment);
  const valve = (id: string, preview: ValveState) => valves ? valves[id] ?? "unknown" : preview;

  return (
    <svg className="schemeCanvas" viewBox="-900 -420 1800 840">
      {/* P1 input pipes */}
      <Pipe d="M -716 -230 L -690 -230 L -690 -165 L -665 -165" active={isActive("b1-v4")} segment="b1-v4" direction={directions?.["b1-v4"]} />
      <Pipe d="M -716 -100 L -640 -100 L -640 -230 L -600 -230" active={isActive("b2-v4")} segment="b2-v4" direction={directions?.["b2-v4"]} />
      <Pipe d="M -535 -165 L -455 -165 L -455 -95 L -390 -95" active={isActive("v4-v6")} segment="v4-v6" direction={directions?.["v4-v6"]} />
      <Pipe d="M -716 70 L -500 70 L -500 -30 L -455 -30" active={isActive("s-v6")} segment="s-v6" direction={directions?.["s-v6"]} />
      <Pipe d="M -325 -30 L -300 -30 L -300 -120 L -170 -120 L -170 -95" active={isActive("v6-v1")} segment="v6-v1" direction={directions?.["v6-v1"]} />
      <Pipe d="M -105 -30 L 2 -30" active={isActive("v1-p1")} segment="v1-p1" direction={directions?.["v1-p1"]} />

      {/* P1 output / reactor / waste pipes */}
      <Pipe d="M -235 -30 L -280 -30 L -280 235 L -105 235 L -105 165" active={isActive("v1-v2")} segment="v1-v2" direction={directions?.["v1-v2"]} />
      <Pipe d="M -170 100 L 185 100 L 185 165 L 206 165" active={isActive("v2-reactor")} segment="v2-reactor" direction={directions?.["v2-reactor"]} />
      <Pipe d="M -235 165 L -320 165 L -320 300 L 608 300" active={isActive("v2-waste")} segment="v2-waste" direction={directions?.["v2-waste"]} />

      {/* P2 branch pipes */}
      <Pipe d="M 335 165 L 405 165" active={isActive("reactor-v3")} segment="reactor-v3" direction={directions?.["reactor-v3"]} />
      <Pipe d="M 535 165 L 632 165" active={isActive("v3-p2")} segment="v3-p2" direction={directions?.["v3-p2"]} />
      <Pipe d="M 470 100 L 470 65" active={isActive("v3-v7")} segment="v3-v7" direction={directions?.["v3-v7"]} />
      <Pipe d="M 470 -65 L 470 -340 L 650 -340 L 650 -309" active={isActive("v7-sf")} segment="v7-sf" direction={directions?.["v7-sf"]} />
      <Pipe d="M 535 0 L 650 0" active={isActive("v7-v8")} segment="v7-v8" direction={directions?.["v7-v8"]} />
      <Pipe d="M 650 -130 L 650 -105" active={isActive("sf-v8")} segment="sf-v8" direction={directions?.["sf-v8"]} />
      <Pipe d="M 715 -65 L 735 -65 L 735 0" active={isActive("v8-v5")} segment="v8-v5" direction={directions?.["v8-v5"]} />
      <Pipe d="M 865 0 L 890 0 L 890 300 L 692 300" active={isActive("v5-waste")} segment="v5-waste" direction={directions?.["v5-waste"]} />
      <Pipe d="M 800 65 L 800 83" active={isActive("v5-column")} segment="v5-column" direction={directions?.["v5-column"]} />
      <Pipe d="M 800 247 L 800 239" active={isActive("column-bottom")} segment="column-bottom" direction={directions?.["column-bottom"]} />
      <Pipe d="M 842 270 L 880 270 L 880 304" active={isActive("bottom-fractions")} segment="bottom-fractions" direction={directions?.["bottom-fractions"]} />

      {/* P1 branch nodes */}
      <Bottle id="B1" x={-760} y={-230} liquidClass="liquidBlue" />
      <Bottle id="B2" x={-760} y={-100} liquidClass="liquidPurple" />
      <Bottle id="S" x={-760} y={70} liquidClass="liquidCyan" />
      <Valve id="V4" x={-600} y={-165} state={valve("V4", "k1k2")} />
      <Valve id="V6" x={-390} y={-30} state={valve("V6", "k1k3")} />
      <Valve id="V1" x={-170} y={-30} state={valve("V1", "k1k3")} />
      <Pump id="P1" x={30} y={-30} />
      <Valve id="V2" x={-170} y={165} state={valve("V2", "closed")} />
      <Reactor x={270} y={165} />

      {/* P2 branch nodes */}
      <Valve id="V3" x={470} y={165} state={valve("V3", "closed")} portMap={{ k1: "right", k2: "top", k3: "left" }} />
      <Pump id="P2" x={660} y={165} />
      <Valve id="V7" x={470} y={0} state={valve("V7", "closed")} rotation={90} />
      <Separator x={650} y={-210} />
      <Valve id="V8" x={650} y={-65} state={valve("V8", "closed")} rotation={90} />
      <Valve id="V5" x={800} y={0} state={valve("V5", "closed")} rotation={180} />
      <Column x={800} y={165} />
      <ColumnBottomValve x={800} y={270} />
      <Waste x={650} y={300} />
      <Fractions x={840} y={340} />

      <text x={-700} y={-350} className="sectionLabel">P1 input / reactor loading</text>
      <text x={410} y={-380} className="sectionLabel">P2 output / SF / column</text>
    </svg>
  );
}

