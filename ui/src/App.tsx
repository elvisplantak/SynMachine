import { useState } from "react";
import "./App.css";

type ValveState = "closed" | "k1k3" | "k1k2";
type ValvePort = "k1" | "k2" | "k3";
type ValveStubPosition = "right" | "left" | "top";
type ValvePortMap = Record<ValvePort, ValveStubPosition>;

function Pipe({ d, active = false }: { d: string; active?: boolean }) {
  return <path d={d} className={active ? "pipe activePipe" : "pipe"} />;
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

function FluidicScheme({ activeSegments = new Set(["b1-v4", "v4-v6", "v6-v1", "v1-p1"]) }: { activeSegments?: Set<string> }) {
  const isActive = (segment: string) => activeSegments.has(segment);

  return (
    <svg className="schemeCanvas" viewBox="-900 -420 1800 840">
      {/* P1 input pipes */}
      <Pipe d="M -716 -230 L -690 -230 L -690 -165 L -665 -165" active={isActive("b1-v4")} />
      <Pipe d="M -716 -100 L -640 -100 L -640 -230 L -600 -230" active={isActive("b2-v4")} />
      <Pipe d="M -535 -165 L -455 -165 L -455 -95 L -390 -95" active={isActive("v4-v6")} />
      <Pipe d="M -716 70 L -500 70 L -500 -30 L -455 -30" active={isActive("s-v6")} />
      <Pipe d="M -325 -30 L -300 -30 L -300 -120 L -170 -120 L -170 -95" active={isActive("v6-v1")} />
      <Pipe d="M -105 -30 L 2 -30" active={isActive("v1-p1")} />

      {/* P1 output / reactor / waste pipes */}
      <Pipe d="M -235 -30 L -280 -30 L -280 235 L -105 235 L -105 165" active={isActive("v1-v2")} />
      <Pipe d="M -170 100 L 185 100 L 185 165 L 206 165" active={isActive("v2-reactor")} />
      <Pipe d="M -235 165 L -320 165 L -320 300 L 608 300" active={isActive("v2-waste")} />

      {/* P2 branch pipes */}
      <Pipe d="M 335 165 L 405 165" active={isActive("reactor-v3")} />
      <Pipe d="M 535 165 L 632 165" active={isActive("v3-p2")} />
      <Pipe d="M 470 100 L 470 65" active={isActive("v3-v7")} />
      <Pipe d="M 470 -65 L 470 -340 L 650 -340 L 650 -309" active={isActive("v7-sf")} />
      <Pipe d="M 535 0 L 650 0" active={isActive("v7-v8")} />
      <Pipe d="M 650 -130 L 650 -105" active={isActive("sf-v8")} />
      <Pipe d="M 715 -65 L 735 -65 L 735 0" active={isActive("v8-v5")} />
      <Pipe d="M 865 0 L 890 0 L 890 300 L 692 300" active={isActive("v5-waste")} />
      <Pipe d="M 800 65 L 800 83" active={isActive("v5-column")} />
      <Pipe d="M 800 247 L 800 239" active={isActive("column-bottom")} />
      <Pipe d="M 842 270 L 880 270 L 880 304" active={isActive("bottom-fractions")} />

      {/* P1 branch nodes */}
      <Bottle id="B1" x={-760} y={-230} liquidClass="liquidBlue" />
      <Bottle id="B2" x={-760} y={-100} liquidClass="liquidPurple" />
      <Bottle id="S" x={-760} y={70} liquidClass="liquidCyan" />
      <Valve id="V4" x={-600} y={-165} state="k1k2" />
      <Valve id="V6" x={-390} y={-30} state="k1k3" />
      <Valve id="V1" x={-170} y={-30} state="k1k3" />
      <Pump id="P1" x={30} y={-30} />
      <Valve id="V2" x={-170} y={165} state="closed" />
      <Reactor x={270} y={165} />

      {/* P2 branch nodes */}
      <Valve id="V3" x={470} y={165} state="closed" portMap={{ k1: "right", k2: "top", k3: "left" }} />
      <Pump id="P2" x={660} y={165} />
      <Valve id="V7" x={470} y={0} state="closed" rotation={90} />
      <Separator x={650} y={-210} />
      <Valve id="V8" x={650} y={-65} state="closed" rotation={90} />
      <Valve id="V5" x={800} y={0} state="closed" rotation={180} />
      <Column x={800} y={165} />
      <ColumnBottomValve x={800} y={270} />
      <Waste x={650} y={300} />
      <Fractions x={840} y={340} />

      <text x={-700} y={-350} className="sectionLabel">P1 input / reactor loading</text>
      <text x={410} y={-380} className="sectionLabel">P2 output / SF / column</text>
    </svg>
  );
}

type ProtocolStepType = "Dose" | "Wait" | "Set mixing" | "Set temperature" | "Reaction hold";
type DoseSource = "" | "B1" | "B2" | "S";
type TimeUnit = "s" | "min";
type PreRunCheckKey =
  | "sourcesAvailable"
  | "p1AndValvesHomed"
  | "reactorEmptyAndClean"
  | "wasteCapacityAvailable";
type PreRunChecks = Record<PreRunCheckKey, boolean>;
type Screen = "dashboard" | "protocolBuilder" | "logs" | "service" | "guidedDemo";
type DemoStage = "configure" | "review" | "live";
type DemoSection = "cockpit" | "log";
type AdditionOrder = "B1 then B2" | "B2 then B1";
type ServiceSection =
  | "overview"
  | "routeTest"
  | "pumps"
  | "valves"
  | "mixerTemperature"
  | "cameras"
  | "diagnostics"
  | "calibration";
type SfBottomValveState = "OPEN" | "CLOSED";
type SfBottomValveCommandStatus = "idle" | "moving" | "confirmed" | "error";
type CommissioningPump = "P1" | "P2";
type PumpServiceCommandStatus = "idle" | "running" | "completed" | "failed";
type PumpServiceState = {
  status: PumpServiceCommandStatus;
  message: string;
  operationCommandId: string | null;
};
type PumpCommissioningFields = {
  workingFull: string;
  workingEmpty: string;
  relativeMove: string;
  targetPosition: string;
  stepInterval: string;
  minimumInterval: string;
  maximumInterval: string;
  defaultInterval: string;
  testStroke: string;
  measuredVolume: string;
};
type LogMode = "human" | "technical";
type LogEvent = {
  time: string;
  message: string;
  subsystem: string;
  level?: "Info" | "Warning" | "Pause";
};
type ExampleRun = {
  id: string;
  name: string;
  date: string;
  status: "Completed" | "Aborted" | "Completed with warnings";
  protocol: string;
  started: string;
  finished: string;
  duration: string;
  stepCount: number;
  humanEvents: LogEvent[];
  technicalEvents: LogEvent[];
};

const exampleRuns: ExampleRun[] = [
  {
    id: "screening-01",
    name: "Screening run 01",
    date: "14 Jul 2026, 09:20",
    status: "Completed",
    protocol: "P1 screening example",
    started: "09:20:00",
    finished: "10:04:18",
    duration: "44 min 18 s",
    stepCount: 7,
    humanEvents: [
      { time: "09:20:00", message: "Run preparation confirmed", subsystem: "Run" },
      { time: "09:20:18", message: "Automatic initialization completed", subsystem: "System" },
      { time: "09:21:04", message: "Mixing started", subsystem: "Reactor" },
      { time: "09:24:32", message: "B1 addition completed", subsystem: "P1" },
      { time: "09:31:10", message: "Target temperature reached", subsystem: "Reactor" },
      { time: "09:31:12", message: "Reaction hold started", subsystem: "Protocol" },
      { time: "10:04:18", message: "Run completed", subsystem: "Run" },
    ],
    technicalEvents: [
      { time: "09:20:03", message: "V4 homing started", subsystem: "V4" },
      { time: "09:20:07", message: "V4 home switch detected", subsystem: "V4" },
      { time: "09:23:58", message: "P1 aspiration command accepted", subsystem: "P1" },
      { time: "09:24:10", message: "P1 aspiration movement completed", subsystem: "P1" },
      { time: "09:24:14", message: "P1 dispense command accepted", subsystem: "P1" },
      { time: "09:31:10", message: "Example temperature sample recorded", subsystem: "Reactor" },
    ],
  },
  {
    id: "screening-02",
    name: "Screening run 02",
    date: "14 Jul 2026, 11:15",
    status: "Completed with warnings",
    protocol: "P1 screening example",
    started: "11:15:00",
    finished: "12:02:41",
    duration: "47 min 41 s",
    stepCount: 7,
    humanEvents: [
      { time: "11:15:00", message: "Run preparation confirmed", subsystem: "Run" },
      { time: "11:15:22", message: "Automatic initialization completed", subsystem: "System" },
      { time: "11:28:09", message: "Run paused for operator review", subsystem: "Run", level: "Pause" },
      { time: "11:31:44", message: "Run resumed after manual confirmation", subsystem: "Run", level: "Warning" },
      { time: "12:02:41", message: "Run completed with warnings", subsystem: "Run", level: "Warning" },
    ],
    technicalEvents: [
      { time: "11:15:04", message: "V4 homing started", subsystem: "V4" },
      { time: "11:15:08", message: "V4 home switch detected", subsystem: "V4" },
      { time: "11:28:09", message: "Reported state changed to paused", subsystem: "Run", level: "Pause" },
      { time: "11:31:44", message: "Manual intervention acknowledged in example log", subsystem: "Operator", level: "Warning" },
      { time: "11:45:16", message: "Example temperature sample recorded", subsystem: "Reactor" },
    ],
  },
  {
    id: "cleaning-validation",
    name: "Cleaning validation test",
    date: "13 Jul 2026, 16:40",
    status: "Aborted",
    protocol: "Cleaning sequence draft",
    started: "16:40:00",
    finished: "16:48:27",
    duration: "8 min 27 s",
    stepCount: 4,
    humanEvents: [
      { time: "16:40:00", message: "Run preparation confirmed", subsystem: "Run" },
      { time: "16:40:20", message: "Automatic initialization completed", subsystem: "System" },
      { time: "16:47:51", message: "Run paused for operator review", subsystem: "Run", level: "Pause" },
      { time: "16:48:27", message: "Run aborted by operator", subsystem: "Run", level: "Warning" },
    ],
    technicalEvents: [
      { time: "16:40:04", message: "V4 homing started", subsystem: "V4" },
      { time: "16:40:08", message: "V4 home switch detected", subsystem: "V4" },
      { time: "16:47:51", message: "Reported state changed to paused", subsystem: "Run", level: "Pause" },
      { time: "16:48:27", message: "Operator abort recorded as example event", subsystem: "Operator", level: "Warning" },
    ],
  },
];

type DoseStep = {
  id: number;
  type: "Dose";
  source: DoseSource;
  volume: string;
  aspirationRate: string;
  dispenseRate: string;
  transitionPolicy: "" | "None" | "Purge to Waste" | "Direct chase to Reactor";
  mixingDuringAddition: "Unchanged" | "On" | "Off";
  delayAfterCompletion: string;
  delayUnit: TimeUnit;
};

type WaitStep = {
  id: number;
  type: "Wait";
  duration: string;
  durationUnit: TimeUnit;
};

type SetMixingStep = {
  id: number;
  type: "Set mixing";
  state: "On" | "Off";
  mixingSpeed: string;
};

type SetTemperatureStep = {
  id: number;
  type: "Set temperature";
  targetTemperature: string;
  continueRule: "Continue immediately" | "Wait until target is reached";
};

type ReactionHoldStep = {
  id: number;
  type: "Reaction hold";
  duration: string;
  durationUnit: TimeUnit | "h";
  startTimer:
    | ""
    | "After reactive addition completes"
    | "After all additions complete"
    | "After target temperature is reached";
};

type ProtocolStep =
  | DoseStep
  | WaitStep
  | SetMixingStep
  | SetTemperatureStep
  | ReactionHoldStep;

const initialProtocolSteps: ProtocolStep[] = [
  { id: 1, type: "Set mixing", state: "On", mixingSpeed: "" },
  {
    id: 2,
    type: "Set temperature",
    targetTemperature: "",
    continueRule: "Continue immediately",
  },
  {
    id: 3,
    type: "Dose",
    source: "B1",
    volume: "",
    aspirationRate: "",
    dispenseRate: "",
    transitionPolicy: "",
    mixingDuringAddition: "Unchanged",
    delayAfterCompletion: "",
    delayUnit: "s",
  },
  {
    id: 4,
    type: "Dose",
    source: "B2",
    volume: "",
    aspirationRate: "",
    dispenseRate: "",
    transitionPolicy: "",
    mixingDuringAddition: "Unchanged",
    delayAfterCompletion: "",
    delayUnit: "s",
  },
  {
    id: 5,
    type: "Dose",
    source: "S",
    volume: "",
    aspirationRate: "",
    dispenseRate: "",
    transitionPolicy: "",
    mixingDuringAddition: "Unchanged",
    delayAfterCompletion: "",
    delayUnit: "s",
  },
  {
    id: 6,
    type: "Reaction hold",
    duration: "",
    durationUnit: "min",
    startTimer: "",
  },
];

function createProtocolStep(type: ProtocolStepType, id: number): ProtocolStep {
  if (type === "Dose") {
    return {
      id,
      type,
      source: "",
      volume: "",
      aspirationRate: "",
      dispenseRate: "",
      transitionPolicy: "",
      mixingDuringAddition: "Unchanged",
      delayAfterCompletion: "",
      delayUnit: "s",
    };
  }

  if (type === "Wait") {
    return { id, type, duration: "", durationUnit: "s" };
  }

  if (type === "Set mixing") {
    return { id, type, state: "On", mixingSpeed: "" };
  }

  if (type === "Set temperature") {
    return { id, type, targetTemperature: "", continueRule: "Continue immediately" };
  }

  return { id, type, duration: "", durationUnit: "min", startTimer: "" };
}

function ProtocolStepFields({
  step,
  onChange,
}: {
  step: ProtocolStep;
  onChange: (step: ProtocolStep) => void;
}) {
  const fieldId = (field: string) => `step-${step.id}-${field}`;

  if (step.type === "Dose") {
    return (
      <div className="protocolFieldGrid protocolDoseFields">
        <label className="protocolField" htmlFor={fieldId("source")}>
          <span>Source</span>
          <select
            id={fieldId("source")}
            value={step.source}
            onChange={(event) => onChange({ ...step, source: event.target.value as DoseSource })}
          >
            <option value="">Not selected</option>
            <option value="B1">B1</option>
            <option value="B2">B2</option>
            <option value="S">S</option>
          </select>
        </label>

        <label className="protocolField" htmlFor={fieldId("volume")}>
          <span>Volume</span>
          <div className="protocolInputWithUnit">
            <input
              id={fieldId("volume")}
              type="number"
              min="0"
              value={step.volume}
              onChange={(event) => onChange({ ...step, volume: event.target.value })}
            />
            <span>ml</span>
          </div>
        </label>

        <label className="protocolField" htmlFor={fieldId("aspiration-rate")}>
          <span>Aspiration rate</span>
          <input
            id={fieldId("aspiration-rate")}
            type="number"
            min="0"
            value={step.aspirationRate}
            onChange={(event) => onChange({ ...step, aspirationRate: event.target.value })}
          />
          <small>unit TBD</small>
        </label>

        <label className="protocolField" htmlFor={fieldId("dispense-rate")}>
          <span>Dispense rate</span>
          <input
            id={fieldId("dispense-rate")}
            type="number"
            min="0"
            value={step.dispenseRate}
            onChange={(event) => onChange({ ...step, dispenseRate: event.target.value })}
          />
          <small>unit TBD</small>
        </label>

        <label className="protocolField" htmlFor={fieldId("transition-policy")}>
          <span>Transition policy</span>
          <select
            id={fieldId("transition-policy")}
            value={step.transitionPolicy}
            onChange={(event) =>
              onChange({
                ...step,
                transitionPolicy: event.target.value as DoseStep["transitionPolicy"],
              })
            }
          >
            <option value="">Not selected</option>
            <option value="None">None</option>
            <option value="Purge to Waste">Purge to Waste</option>
            <option value="Direct chase to Reactor">Direct chase to Reactor</option>
          </select>
        </label>

        <label className="protocolField" htmlFor={fieldId("mixing-during-addition")}>
          <span>Mixing during addition</span>
          <select
            id={fieldId("mixing-during-addition")}
            value={step.mixingDuringAddition}
            onChange={(event) =>
              onChange({
                ...step,
                mixingDuringAddition: event.target.value as DoseStep["mixingDuringAddition"],
              })
            }
          >
            <option value="Unchanged">Unchanged</option>
            <option value="On">On</option>
            <option value="Off">Off</option>
          </select>
        </label>

        <label className="protocolField" htmlFor={fieldId("delay")}>
          <span>Delay after completion</span>
          <div className="protocolInputWithUnit">
            <input
              id={fieldId("delay")}
              type="number"
              min="0"
              value={step.delayAfterCompletion}
              onChange={(event) => onChange({ ...step, delayAfterCompletion: event.target.value })}
            />
            <select
              aria-label={`Step ${step.id} delay unit`}
              value={step.delayUnit}
              onChange={(event) =>
                onChange({ ...step, delayUnit: event.target.value as DoseStep["delayUnit"] })
              }
            >
              <option value="s">s</option>
              <option value="min">min</option>
            </select>
          </div>
        </label>
      </div>
    );
  }

  if (step.type === "Wait") {
    return (
      <div className="protocolFieldGrid">
        <label className="protocolField" htmlFor={fieldId("duration")}>
          <span>Duration</span>
          <div className="protocolInputWithUnit">
            <input
              id={fieldId("duration")}
              type="number"
              min="0"
              value={step.duration}
              onChange={(event) => onChange({ ...step, duration: event.target.value })}
            />
            <select
              aria-label={`Step ${step.id} duration unit`}
              value={step.durationUnit}
              onChange={(event) =>
                onChange({ ...step, durationUnit: event.target.value as WaitStep["durationUnit"] })
              }
            >
              <option value="s">s</option>
              <option value="min">min</option>
            </select>
          </div>
        </label>
      </div>
    );
  }

  if (step.type === "Set mixing") {
    return (
      <div className="protocolFieldGrid">
        <label className="protocolField" htmlFor={fieldId("state")}>
          <span>State</span>
          <select
            id={fieldId("state")}
            value={step.state}
            onChange={(event) =>
              onChange({ ...step, state: event.target.value as SetMixingStep["state"] })
            }
          >
            <option value="On">On</option>
            <option value="Off">Off</option>
          </select>
        </label>

        <label className="protocolField" htmlFor={fieldId("mixing-speed")}>
          <span>Mixing speed <small>Optional</small></span>
          <input
            id={fieldId("mixing-speed")}
            type="number"
            min="0"
            value={step.mixingSpeed}
            onChange={(event) => onChange({ ...step, mixingSpeed: event.target.value })}
          />
          <small>unit TBD</small>
        </label>
      </div>
    );
  }

  if (step.type === "Set temperature") {
    return (
      <div className="protocolFieldGrid">
        <label className="protocolField" htmlFor={fieldId("target-temperature")}>
          <span>Target temperature</span>
          <div className="protocolInputWithUnit">
            <input
              id={fieldId("target-temperature")}
              type="number"
              value={step.targetTemperature}
              onChange={(event) => onChange({ ...step, targetTemperature: event.target.value })}
            />
            <span>°C</span>
          </div>
        </label>

        <label className="protocolField" htmlFor={fieldId("continue-rule")}>
          <span>Continue rule</span>
          <select
            id={fieldId("continue-rule")}
            value={step.continueRule}
            onChange={(event) =>
              onChange({
                ...step,
                continueRule: event.target.value as SetTemperatureStep["continueRule"],
              })
            }
          >
            <option value="Continue immediately">Continue immediately</option>
            <option value="Wait until target is reached">Wait until target is reached</option>
          </select>
        </label>
      </div>
    );
  }

  return (
    <div className="protocolFieldGrid">
      <label className="protocolField" htmlFor={fieldId("duration")}>
        <span>Duration</span>
        <div className="protocolInputWithUnit">
          <input
            id={fieldId("duration")}
            type="number"
            min="0"
            value={step.duration}
            onChange={(event) => onChange({ ...step, duration: event.target.value })}
          />
          <select
            aria-label={`Step ${step.id} duration unit`}
            value={step.durationUnit}
            onChange={(event) =>
              onChange({ ...step, durationUnit: event.target.value as ReactionHoldStep["durationUnit"] })
            }
          >
            <option value="s">s</option>
            <option value="min">min</option>
            <option value="h">h</option>
          </select>
        </div>
      </label>

      <label className="protocolField" htmlFor={fieldId("start-timer")}>
        <span>Start timer</span>
        <select
          id={fieldId("start-timer")}
          value={step.startTimer}
          onChange={(event) =>
            onChange({
              ...step,
              startTimer: event.target.value as ReactionHoldStep["startTimer"],
            })
          }
        >
          <option value="">Not selected</option>
          <option value="After reactive addition completes">After reactive addition completes</option>
          <option value="After all additions complete">After all additions complete</option>
          <option value="After target temperature is reached">
            After target temperature is reached
          </option>
        </select>
      </label>
    </div>
  );
}

function ProtocolStepCard({
  step,
  index,
  stepCount,
  onChange,
  onMove,
  onRemove,
}: {
  step: ProtocolStep;
  index: number;
  stepCount: number;
  onChange: (step: ProtocolStep) => void;
  onMove: (index: number, direction: -1 | 1) => void;
  onRemove: (id: number) => void;
}) {
  return (
    <article className="protocolStepCard">
      <div className="protocolStepHeader">
        <div>
          <span className="protocolStepNumber">Step {index + 1}</span>
          <h3>{step.type}</h3>
        </div>
        <div className="protocolStepActions" aria-label={`Step ${index + 1} controls`}>
          <button type="button" disabled={index === 0} onClick={() => onMove(index, -1)}>
            Move up
          </button>
          <button
            type="button"
            disabled={index === stepCount - 1}
            onClick={() => onMove(index, 1)}
          >
            Move down
          </button>
          <button className="protocolRemoveButton" type="button" onClick={() => onRemove(step.id)}>
            Remove
          </button>
        </div>
      </div>
      <ProtocolStepFields step={step} onChange={onChange} />
    </article>
  );
}

function TopNavigation({
  activeScreen,
  onNavigate,
}: {
  activeScreen: Screen;
  onNavigate: (screen: Screen) => void;
}) {
  return (
    <nav className="topNavigation" aria-label="Primary navigation">
      <button
        className="topNavigationItem"
        type="button"
        aria-current={activeScreen === "dashboard" ? "page" : undefined}
        onClick={() => onNavigate("dashboard")}
      >
        Dashboard
      </button>
      <button
        className="topNavigationItem"
        type="button"
        aria-current={activeScreen === "protocolBuilder" ? "page" : undefined}
        onClick={() => onNavigate("protocolBuilder")}
      >
        Protocol Builder
      </button>
      <button
        className="topNavigationItem"
        type="button"
        aria-current={activeScreen === "logs" ? "page" : undefined}
        onClick={() => onNavigate("logs")}
      >
        Logs
      </button>
      <button
        className="topNavigationItem serviceNavigationItem"
        type="button"
        aria-current={activeScreen === "service" ? "page" : undefined}
        onClick={() => onNavigate("service")}
      >
        Service
      </button>
    </nav>
  );
}

const serviceSections: { id: ServiceSection; label: string }[] = [
  { id: "overview", label: "System overview" },
  { id: "routeTest", label: "Route test" },
  { id: "pumps", label: "Pumps" },
  { id: "valves", label: "Valves" },
  { id: "mixerTemperature", label: "Mixer & temperature" },
  { id: "cameras", label: "Cameras" },
  { id: "diagnostics", label: "Diagnostics" },
  { id: "calibration", label: "Calibration" },
];

function DisabledServiceButton({ children }: { children: string }) {
  return <button type="button" disabled aria-disabled="true">{children}</button>;
}

function SfBottomValveServiceControl() {
  const [confirmedState, setConfirmedState] = useState<SfBottomValveState | null>(null);
  const [commandStatus, setCommandStatus] = useState<SfBottomValveCommandStatus>("idle");
  const [message, setMessage] = useState("No position has been confirmed in this UI session.");

  const commandState = async (state: SfBottomValveState) => {
    setCommandStatus("moving");
    setMessage(`Moving SF bottom valve to ${state}…`);

    try {
      const response = await fetch("/api/v1/service/sf-bottom-valve", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ state }),
      });
      const payload = await response.json().catch(() => null) as {
        detail?: string;
        position_confirmed?: boolean;
        state?: SfBottomValveState;
      } | null;

      if (!response.ok || payload?.position_confirmed !== true || payload.state !== state) {
        throw new Error(payload?.detail ?? `Backend returned HTTP ${response.status}`);
      }

      setConfirmedState(state);
      setCommandStatus("confirmed");
      setMessage(`${state} position confirmed by the actuator.`);
    } catch (error) {
      setCommandStatus("error");
      setMessage(error instanceof Error ? error.message : "Unknown backend error");
    }
  };

  return (
    <section className="serviceGroup sfBottomValveCard" aria-labelledby="sf-bottom-valve-heading">
      <div className="sfBottomValveHeading">
        <div>
          <h3 id="sf-bottom-valve-heading">SF bottom valve</h3>
          <span>Dynamixel XL430-W250-T · U2D2</span>
        </div>
        <strong className={`sfBottomValveStatus ${commandStatus}`}>
          {commandStatus === "moving" ? "Moving" : confirmedState ?? "Unknown"}
        </strong>
      </div>
      <div className="serviceStatusList">
        <span>Last confirmed state<strong>{confirmedState ?? "Not confirmed"}</strong></span>
        <span>Command result<strong>{message}</strong></span>
      </div>
      <div className="serviceActionRow">
        <button type="button" disabled={commandStatus === "moving"} onClick={() => void commandState("OPEN")}>Open</button>
        <button type="button" disabled={commandStatus === "moving"} onClick={() => void commandState("CLOSED")}>Close</button>
      </div>
      <p className="serviceControlNotice">Direct hardware command through the backend. Keep the mechanism supervised.</p>
    </section>
  );
}

const initialPumpServiceState: PumpServiceState = {
  status: "idle",
  message: "No command has been executed in this UI session.",
  operationCommandId: null,
};

function PumpServiceControl({ pump }: { pump: CommissioningPump }) {
  const [targetSteps, setTargetSteps] = useState("2000");
  const [safeRouteConfirmed, setSafeRouteConfirmed] = useState(false);
  const [commandState, setCommandState] = useState<PumpServiceState>(initialPumpServiceState);
  const running = commandState.status === "running";
  const parsedTarget = Number(targetSteps);
  const targetValid = Number.isInteger(parsedTarget) && parsedTarget >= 1 && parsedTarget <= 20500;

  const executeCommand = async (command: "HOME" | "MOVE_ABSOLUTE_STEPS") => {
    if (!safeRouteConfirmed || (command === "MOVE_ABSOLUTE_STEPS" && !targetValid)) {
      return;
    }

    const operationCommandId = crypto.randomUUID();
    const phaseExecutionId = `service-${pump.toLowerCase()}-${Date.now()}`;
    setCommandState({
      status: "running",
      message: command === "HOME" ? `Homing ${pump}…` : `Moving ${pump} to ${parsedTarget} steps…`,
      operationCommandId,
    });

    try {
      const response = await fetch("/api/v1/service/pumps/command", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          phase_execution_id: phaseExecutionId,
          operation_command_id: operationCommandId,
          pump,
          command,
          ...(command === "MOVE_ABSOLUTE_STEPS" ? { target_steps: parsedTarget } : {}),
          safe_route_confirmed: true,
        }),
      });
      const payload = await response.json().catch(() => null) as {
        detail?: string;
        operation_command_id?: string;
        state?: string;
        error_code?: string | null;
        execution_started?: boolean | null;
      } | null;

      if (!response.ok) {
        throw new Error(payload?.detail ?? `Backend returned HTTP ${response.status}`);
      }
      if (payload?.operation_command_id !== operationCommandId || payload.state !== "COMPLETED") {
        const failure = payload?.error_code ? ` (${payload.error_code})` : "";
        throw new Error(`Command ended in ${payload?.state ?? "an unknown state"}${failure}.`);
      }

      setCommandState({
        status: "completed",
        message: command === "HOME"
          ? `${pump} HOME completed.`
          : `${pump} reached ${parsedTarget} steps.`,
        operationCommandId,
      });
    } catch (error) {
      setCommandState({
        status: "failed",
        message: error instanceof Error ? error.message : "Unknown backend error",
        operationCommandId,
      });
    }
  };

  return (
    <section className="serviceGroup pumpServiceCard" aria-labelledby={`${pump}-service-heading`}>
      <div className="pumpServiceHeading">
        <div>
          <h3 id={`${pump}-service-heading`}>{pump} syringe pump</h3>
          <span>Arduino Mega · absolute range 1–20500 steps</span>
        </div>
        <strong className={`pumpServiceStatus ${commandState.status}`}>
          {running ? "Running" : commandState.status}
        </strong>
      </div>
      <div className="serviceStatusList">
        <span>Last command result<strong>{commandState.message}</strong></span>
        <span>Operation command ID<strong>{commandState.operationCommandId ?? "Not assigned"}</strong></span>
      </div>
      <label className="pumpTargetField">
        Absolute target, steps
        <input
          type="number"
          min="1"
          max="20500"
          step="1"
          value={targetSteps}
          disabled={running}
          onChange={(event) => setTargetSteps(event.target.value)}
        />
      </label>
      {!targetValid && <p className="commissioningValidation" role="alert">Target must be a whole number from 1 to 20500.</p>}
      <label className="safeRouteConfirmation">
        <input
          type="checkbox"
          checked={safeRouteConfirmed}
          disabled={running}
          onChange={(event) => setSafeRouteConfirmed(event.target.checked)}
        />
        I have physically confirmed a safe fluid route for this pump command.
      </label>
      <div className="serviceActionRow">
        <button type="button" disabled={running || !safeRouteConfirmed} onClick={() => void executeCommand("HOME")}>Home</button>
        <button type="button" disabled={running || !safeRouteConfirmed || !targetValid} onClick={() => void executeCommand("MOVE_ABSOLUTE_STEPS")}>Move to position</button>
      </div>
      <p className="serviceControlNotice">Supervised direct hardware command. Unknown outcomes are not retried automatically.</p>
    </section>
  );
}

const emptyPumpCommissioningFields: PumpCommissioningFields = {
  workingFull: "",
  workingEmpty: "",
  relativeMove: "",
  targetPosition: "",
  stepInterval: "",
  minimumInterval: "",
  maximumInterval: "",
  defaultInterval: "",
  testStroke: "",
  measuredVolume: "",
};

function PumpCommissioning() {
  const [selectedPump, setSelectedPump] = useState<CommissioningPump>("P1");
  const [pumpFields, setPumpFields] = useState<Record<CommissioningPump, PumpCommissioningFields>>({
    P1: { ...emptyPumpCommissioningFields },
    P2: { ...emptyPumpCommissioningFields },
  });
  const [primeCycles, setPrimeCycles] = useState<Record<CommissioningPump, string>>({ P1: "2", P2: "2" });
  const fields = pumpFields[selectedPump];
  const stroke = Number(fields.testStroke);
  const volume = Number(fields.measuredVolume);
  const hasCalibrationInput = fields.testStroke !== "" || fields.measuredVolume !== "";
  const calibrationValid = stroke > 0 && volume > 0;
  const calculatedStepsPerMl = calibrationValid ? (stroke / volume).toFixed(2) : "";

  const updateField = (field: keyof PumpCommissioningFields, value: string) => {
    setPumpFields((current) => ({
      ...current,
      [selectedPump]: { ...current[selectedPump], [field]: value },
    }));
  };

  return (
    <section className="pumpCommissioning" aria-labelledby="pump-commissioning-heading">
      <div className="commissioningHeading">
        <div>
          <span className="panelEyebrow">Local engineering draft</span>
          <h2 id="pump-commissioning-heading">Pump commissioning — {selectedPump}</h2>
          <p>Raw-step preparation for later experimental calibration and controlled pump testing.</p>
        </div>
        <span className="commissioningBadge pendingBadge">Pending calibration</span>
      </div>

      <div className="pumpSelector" aria-label="Pump selection">
        {(["P1", "P2"] as const).map((pump) => (
          <button key={pump} type="button" aria-pressed={selectedPump === pump} onClick={() => setSelectedPump(pump)}>
            <span>{pump}</span>
            {selectedPump === pump && <small>Selected</small>}
          </button>
        ))}
      </div>

      <div className="commissioningNotice" role="note">Live HOME and absolute-position actions are available in the pump cards above. Calibration and speed controls remain inactive.</div>

      <section className="commissioningBlock">
        <div className="commissioningBlockTitle"><h3>Current information</h3><span className="commissioningBadge confirmedBadge">Confirmed orientation</span></div>
        <dl className="commissioningInfoGrid">
          <div><dt>Selected pump</dt><dd>{selectedPump}</dd></div>
          <div><dt>Hardware connection</dt><dd>Service command path available above</dd></div>
          <div><dt>Homing state</dt><dd>Not persisted in this UI session</dd></div>
          <div><dt>Current position</dt><dd>Unavailable</dd></div>
          <div><dt>Syringe capacity</dt><dd>20 mL</dd></div>
          <div><dt>Home position</dt><dd>0 steps</dd></div>
          <div><dt>Recovered max travel</dt><dd>20500 steps</dd></div>
          <div><dt>Aspiration direction</dt><dd>Toward 0</dd></div>
          <div><dt>Dispense direction</dt><dd>Toward 20500</dd></div>
        </dl>
        <p className="commissioningExplanation">Near 0 the syringe chamber volume is maximal; near 20500 it is minimal and the syringe is practically empty. Both pumps share this confirmed orientation. The 20500-step endpoint is a recovered software travel limit, not a validated volume calibration.</p>
      </section>

      <div className="commissioningTwoColumn">
        <section className="commissioningBlock">
          <div className="commissioningBlockTitle"><h3>Position commissioning</h3><span className="commissioningBadge referenceBadge">Recovered interval: 0–20500 steps</span></div>
          <div className="commissioningFieldGrid">
            <label>Working full position, steps<input type="number" value={fields.workingFull} placeholder="Not calibrated" onChange={(event) => updateField("workingFull", event.target.value)} /></label>
            <label>Working empty position, steps<input type="number" value={fields.workingEmpty} placeholder="Not calibrated" onChange={(event) => updateField("workingEmpty", event.target.value)} /></label>
            <label>Relative move, steps<input type="number" value={fields.relativeMove} placeholder="Enter steps" onChange={(event) => updateField("relativeMove", event.target.value)} /></label>
            <label>Target position, steps<input type="number" value={fields.targetPosition} placeholder="Enter 0–20500" onChange={(event) => updateField("targetPosition", event.target.value)} /></label>
          </div>
          <p className="commissioningExplanation">Working positions will later be chosen experimentally inside the physical endpoints; no endpoint margins are assumed here.</p>
          <div className="serviceActionRow"><DisabledServiceButton>Home selected pump</DisabledServiceButton><DisabledServiceButton>Move relative</DisabledServiceButton><DisabledServiceButton>Move to position</DisabledServiceButton><DisabledServiceButton>Stop motion</DisabledServiceButton></div>
        </section>

        <section className="commissioningBlock">
          <div className="commissioningBlockTitle"><h3>Speed commissioning</h3><span className="commissioningBadge pendingBadge">Limits not validated</span></div>
          <div className="commissioningFieldGrid">
            <label>Step interval, µs<input type="number" value={fields.stepInterval} placeholder="Enter interval" onChange={(event) => updateField("stepInterval", event.target.value)} /></label>
            <label>Minimum tested interval, µs<input type="number" value={fields.minimumInterval} placeholder="Not calibrated" onChange={(event) => updateField("minimumInterval", event.target.value)} /></label>
            <label>Maximum tested interval, µs<input type="number" value={fields.maximumInterval} placeholder="Not calibrated" onChange={(event) => updateField("maximumInterval", event.target.value)} /></label>
            <label>Default interval, µs<input type="number" value={fields.defaultInterval} placeholder="Not calibrated" onChange={(event) => updateField("defaultInterval", event.target.value)} /></label>
          </div>
          <div className="serviceActionRow"><DisabledServiceButton>Apply speed</DisabledServiceButton><DisabledServiceButton>Run speed test</DisabledServiceButton></div>
        </section>
      </div>

      <section className="commissioningBlock">
        <div className="commissioningBlockTitle"><h3>Volume calibration</h3><span className="commissioningBadge pendingBadge">Experimental only</span></div>
        <div className="commissioningFieldGrid calibrationFields">
          <label>Test stroke, steps<input type="number" min="0" value={fields.testStroke} placeholder="Enter positive steps" onChange={(event) => updateField("testStroke", event.target.value)} /></label>
          <label>Measured volume, mL<input type="number" min="0" step="any" value={fields.measuredVolume} placeholder="Enter positive volume" onChange={(event) => updateField("measuredVolume", event.target.value)} /></label>
          <label>Calculated steps/mL<input type="text" readOnly value={calculatedStepsPerMl} placeholder="Not calculated" /></label>
        </div>
        {hasCalibrationInput && !calibrationValid && <p className="commissioningValidation" role="alert">Test stroke and measured volume must both be positive.</p>}
        <p className="commissioningExplanation">Experimental calibration only — not saved or applied to firmware. This draft does not claim volumetric accuracy.</p>
        <div className="serviceActionRow"><DisabledServiceButton>Run calibration stroke</DisabledServiceButton></div>
      </section>

      <div className="commissioningTwoColumn primingGrid">
        <section className="commissioningBlock">
          <div className="commissioningBlockTitle"><h3>P1 priming configuration</h3><span className="commissioningBadge confirmedBadge">Confirmed demo plan</span></div>
          <dl className="commissioningCompactList"><div><dt>Route</dt><dd>S → P1 → Waste</dd></div><div><dt>Prime stroke</dt><dd>Pending calibration</dd></div><div><dt>Purpose</dt><dd>Remove air before precision B1/B2 dosing</dd></div></dl>
          <label className="commissioningSingleField">Prime cycles<input type="number" min="1" value={primeCycles.P1} onChange={(event) => setPrimeCycles((current) => ({ ...current, P1: event.target.value }))} /></label>
          <p className="commissioningExplanation">Priming content goes to Waste, never back into the S bottle.</p>
          <div className="serviceActionRow"><DisabledServiceButton>Run P1 prime test</DisabledServiceButton></div>
        </section>
        <section className="commissioningBlock">
          <div className="commissioningBlockTitle"><h3>P2 priming configuration</h3><span className="commissioningBadge confirmedBadge">Confirmed demo plan</span></div>
          <dl className="commissioningCompactList"><div><dt>Route</dt><dd>Reactor S → P2 → Reactor</dd></div><div><dt>Prime stroke</dt><dd>Pending calibration</dd></div><div><dt>Timing</dt><dd>After S enters Reactor, before reaction-liquid transfer</dd></div><div><dt>Purpose</dt><dd>Reduce air in P2 and the Reactor-to-P2 inlet path</dd></div></dl>
          <label className="commissioningSingleField">Prime cycles<input type="number" min="1" value={primeCycles.P2} onChange={(event) => setPrimeCycles((current) => ({ ...current, P2: event.target.value }))} /></label>
          <div className="serviceActionRow"><DisabledServiceButton>Run P2 prime test</DisabledServiceButton></div>
        </section>
      </div>

      <aside className="commissioningEngineeringNote">
        <strong>Startup and homing note</strong>
        <ul><li>Normal cold startup requires homing all confirmed motorized valves and both pumps.</li><li>Pump homing is not repeated before every normal stroke.</li><li>Re-homing is required after loss of trusted position, including power interruption or interrupted motion.</li><li>The Column bottom valve uses its separately confirmed 4° CLOSED and 94° OPEN positions.</li></ul>
      </aside>
    </section>
  );
}

function ServiceSectionContent({ section }: { section: ServiceSection }) {
  if (section === "overview") {
    const groups = [
      ["Connections", ["Backend", "Arduino Mega"]],
      ["P1 subsystem", ["P1", "V1", "V2", "V4", "V6"]],
      ["P2 subsystem", ["P2", "V3", "V5", "V7", "V8"]],
      ["Reactor", ["Mixer", "Reactor temperature"]],
      ["Cameras", ["Reactor camera", "Overview camera"]],
    ] as const;
    return (
      <>
        <div className="serviceSectionHeading"><span className="panelEyebrow">Hardware structure</span><h2>System overview</h2><p>Confirmed subsystem placeholders for future connection and diagnostics.</p></div>
        <div className="serviceOverviewGrid">
          {groups.map(([group, items]) => (
            <section key={group} className="serviceGroup"><h3>{group}</h3>{items.map((item) => <div className="serviceStatusRow" key={item}><strong>{item}</strong><span>Not connected</span></div>)}</section>
          ))}
        </div>
        <div className="serviceInfoNote">Frontend placeholders only. These values are not live hardware data and do not confirm independent device feedback.</div>
      </>
    );
  }

  if (section === "routeTest") {
    return (
      <>
        <div className="serviceSectionHeading"><span className="panelEyebrow">Structural draft</span><h2>Route test</h2><p>A future backend will validate physical route availability and safety.</p></div>
        <div className="serviceFormGrid">
          <label>Source<select disabled aria-disabled="true"><option>B1</option><option>B2</option><option>S</option><option>Reactor</option></select></label>
          <label>Destination<select disabled aria-disabled="true"><option>Reactor</option><option>Waste</option><option>Separatory funnel</option><option>Column</option></select></label>
          <label>Volume<input disabled aria-disabled="true" placeholder="Not configured" /></label>
        </div>
        <div className="routePreviewDraft"><span>Route preview</span><strong>Not calculated</strong><p>No source-to-destination combination is validated in this frontend draft.</p></div>
        <div className="serviceActionRow"><DisabledServiceButton>Preview route</DisabledServiceButton><DisabledServiceButton>Run route test</DisabledServiceButton></div>
      </>
    );
  }

  if (section === "pumps") {
    return (
      <>
        <div className="serviceSectionHeading servicePumpsHeading"><span className="panelEyebrow">Supervised hardware service</span><h2>Pumps</h2><p>P1 and P2 expose HOME and raw absolute-step positioning through the durable backend command path. Volume control remains pending calibration.</p></div>
        <div className="serviceTwoColumn pumpSummaryGrid">{(["P1", "P2"] as const).map((pump) => <PumpServiceControl pump={pump} key={pump} />)}</div>
        <PumpCommissioning />
      </>
    );
  }

  if (section === "valves") {
    return (
      <>
        <div className="serviceSectionHeading"><span className="panelEyebrow">Valve control</span><h2>Valves</h2><p>V1–V8 remain disabled in this UI checkpoint. The separately connected SF bottom valve is available through its confirmed backend adapter.</p></div>
        <SfBottomValveServiceControl />
        <div className="valveServiceGrid">{Array.from({ length: 8 }, (_, index) => `V${index + 1}`).map((valve) => <section className="serviceGroup valveServiceCard" key={valve}><div><h3>{valve}</h3><span>State: Unknown</span></div><div className="serviceActionRow"><DisabledServiceButton>Home</DisabledServiceButton><DisabledServiceButton>Closed</DisabledServiceButton><DisabledServiceButton>k1 ↔ k3</DisabledServiceButton><DisabledServiceButton>k1 ↔ k2</DisabledServiceButton></div></section>)}</div>
      </>
    );
  }

  if (section === "mixerTemperature") {
    return (
      <>
        <div className="serviceSectionHeading"><span className="panelEyebrow">Reactor subsystem draft</span><h2>Mixer & temperature</h2><p>Backend safety rules remain active in Service mode.</p></div>
        <div className="serviceTwoColumn"><section className="serviceGroup"><h3>Mixer</h3><div className="serviceStatusList"><span>Connection<strong>Not connected</strong></span><span>Commanded speed<strong>Not configured · unit TBD</strong></span></div><div className="serviceActionRow"><DisabledServiceButton>Start</DisabledServiceButton><DisabledServiceButton>Stop</DisabledServiceButton></div></section><section className="serviceGroup"><h3>Reactor temperature</h3><div className="serviceStatusList"><span>Target temperature<strong>Not configured</strong></span><span>Heater state<strong>Unknown</strong></span><span>Reported temperature<strong>Not connected</strong></span></div><div className="serviceActionRow"><DisabledServiceButton>Apply target</DisabledServiceButton></div></section></div>
      </>
    );
  }

  if (section === "cameras") {
    return (
      <>
        <div className="serviceSectionHeading"><span className="panelEyebrow">Planned media hardware</span><h2>Cameras</h2><p>No live feed, storage, or playback is implemented.</p></div>
        <div className="serviceTwoColumn">{[["Reactor camera", "Reactor observation"], ["Overview camera", "System overview"]].map(([camera, role]) => <section className="serviceGroup cameraServiceCard" key={camera}><div className="cameraServicePlaceholder">No video stream</div><h3>{camera}</h3><div className="serviceStatusList"><span>Role<strong>{role}</strong></span><span>Connection<strong>Not connected</strong></span><span>Stream<strong>Not implemented</strong></span><span>Recording<strong>Not implemented</strong></span></div></section>)}</div>
      </>
    );
  }

  if (section === "diagnostics") {
    const diagnostics = [["Connection diagnostics", "Backend not connected"], ["Homing diagnostics", "No live diagnostic data"], ["Switch and input diagnostics", "No live diagnostic data"], ["Command history", "No command history in frontend draft"], ["Last reported fault", "No reported faults in frontend draft"]];
    return <><div className="serviceSectionHeading"><span className="panelEyebrow">Future diagnostic structure</span><h2>Diagnostics</h2><p>No serial messages, raw inputs, or live fault data are available.</p></div><div className="diagnosticsList">{diagnostics.map(([name, state]) => <div key={name}><strong>{name}</strong><span>{state}</span></div>)}</div></>;
  }

  const calibrations = ["P1 volume calibration", "P2 volume calibration", "Valve home offsets", "Mixer calibration", "Reactor temperature calibration", "Camera calibration"];
  return <><div className="serviceSectionHeading"><span className="panelEyebrow">Planning only</span><h2>Calibration</h2><p>No procedures or existing calibration values are defined.</p></div><div className="calibrationList">{calibrations.map((item) => <div key={item}><strong>{item}</strong><DisabledServiceButton>Unavailable</DisabledServiceButton></div>)}</div><div className="serviceWarningNote">Calibration values affect physical execution and will require validation before use.</div></>;
}

function ServiceScreen({ onNavigate }: { onNavigate: (screen: Screen) => void }) {
  const [activeSection, setActiveSection] = useState<ServiceSection>("overview");
  return (
    <main className="appShell serviceShell">
      <header className="topBar serviceTopBar"><div><div className="serviceHeadingRow"><div className="brand">Service</div><div className="serviceDraftLabel">Supervised hardware service</div></div><div className="subBrand">Manual control, diagnostics, and calibration</div></div><div className="topBarActions"><TopNavigation activeScreen="service" onNavigate={onNavigate} /></div></header>
      <div className="serviceLayout">
        <aside className="serviceNavigation" aria-label="Service sections"><span className="panelEyebrow">Technical workspace</span>{serviceSections.map((section) => <button key={section.id} type="button" aria-pressed={activeSection === section.id} onClick={() => setActiveSection(section.id)}>{section.label}</button>)}<p>Only explicitly enabled controls are live. Service mode does not bypass backend safety rules.</p></aside>
        <section className="serviceContent"><ServiceSectionContent section={activeSection} /></section>
      </div>
    </main>
  );
}

function LogsScreen({ onNavigate }: { onNavigate: (screen: Screen) => void }) {
  const [selectedRunId, setSelectedRunId] = useState(exampleRuns[0].id);
  const [logMode, setLogMode] = useState<LogMode>("human");
  const selectedRun = exampleRuns.find((run) => run.id === selectedRunId) ?? exampleRuns[0];
  const visibleEvents = logMode === "human" ? selectedRun.humanEvents : selectedRun.technicalEvents;

  return (
    <main className="appShell">
      <header className="topBar logsTopBar">
        <div>
          <div className="logsHeadingRow">
            <div className="brand">Logs</div>
            <div className="exampleDataLabel">Example data</div>
          </div>
          <div className="subBrand">Run history, event timeline, and technical diagnostics</div>
        </div>
        <div className="topBarActions">
          <TopNavigation activeScreen="logs" onNavigate={onNavigate} />
        </div>
      </header>

      <div className="logsLayout">
        <aside className="runHistoryPanel" aria-labelledby="run-history-title">
          <div className="logsPanelHeading">
            <span className="panelEyebrow">Frontend example dataset</span>
            <h2 id="run-history-title">Run history</h2>
          </div>
          <div className="runHistoryList">
            {exampleRuns.map((run) => (
              <button
                key={run.id}
                className="runHistoryItem"
                type="button"
                aria-pressed={selectedRun.id === run.id}
                onClick={() => setSelectedRunId(run.id)}
              >
                <span className="runHistoryItemTop">
                  <strong>{run.name}</strong>
                  <span className={`runStatus runStatus${run.status.replaceAll(" ", "")}`}>
                    {run.status}
                  </span>
                </span>
                <span>{run.date}</span>
                <span>{run.protocol}</span>
              </button>
            ))}
          </div>
          <p className="exampleDataNote">Local example content only. No run database is connected.</p>
        </aside>

        <div className="logsMainColumn">
          <section className="logsPanel runSummaryPanel" aria-labelledby="selected-run-title">
            <div className="logsPanelHeading">
              <span className="panelEyebrow">Selected example run</span>
              <h2 id="selected-run-title">{selectedRun.name}</h2>
            </div>
            <dl className="selectedRunSummary">
              <div><dt>Protocol</dt><dd>{selectedRun.protocol}</dd></div>
              <div><dt>Status</dt><dd>{selectedRun.status}</dd></div>
              <div><dt>Started</dt><dd>{selectedRun.started}</dd></div>
              <div><dt>Finished</dt><dd>{selectedRun.finished}</dd></div>
              <div><dt>Duration</dt><dd>{selectedRun.duration}</dd></div>
              <div><dt>Step count</dt><dd>{selectedRun.stepCount}</dd></div>
            </dl>
          </section>

          <section className="logsPanel timelinePanel" aria-labelledby="event-timeline-title">
            <div className="timelineHeader">
              <div className="logsPanelHeading">
                <span className="panelEyebrow">Example events</span>
                <h2 id="event-timeline-title">Event timeline</h2>
              </div>
              <div className="logModeSwitch" aria-label="Log detail level">
                <button type="button" aria-pressed={logMode === "human"} onClick={() => setLogMode("human")}>Human log</button>
                <button type="button" aria-pressed={logMode === "technical"} onClick={() => setLogMode("technical")}>Technical log</button>
              </div>
            </div>
            <ol className="eventTimeline">
              {visibleEvents.map((event, index) => (
                <li key={`${event.time}-${index}`}>
                  <time>{event.time}</time>
                  <div className="eventMarker" aria-hidden="true" />
                  <div className="eventContent">
                    <strong>{event.message}</strong>
                    <span>{event.subsystem} · {event.level ?? "Info"}</span>
                  </div>
                </li>
              ))}
            </ol>
          </section>

          <section className="logsPanel executionComparison" aria-labelledby="execution-comparison-title">
            <div className="logsPanelHeading">
              <span className="panelEyebrow">Example distinction</span>
              <h2 id="execution-comparison-title">Planned versus reported execution</h2>
            </div>
            <div className="executionComparisonGrid">
              <div><h3>Planned</h3><p>Dose B1</p><p>Commanded volume: 2.0 ml</p></div>
              <div><h3>Reported execution</h3><p>Pump movement completed</p><p>No independent delivered-volume measurement available</p></div>
            </div>
          </section>

          <div className="logsLowerGrid">
            <section className="logsPanel telemetryPlaceholder" aria-labelledby="telemetry-title">
              <div className="logsPanelHeading"><span className="panelEyebrow">Example visualization</span><h2 id="telemetry-title">Reactor temperature telemetry</h2></div>
              <svg viewBox="0 0 500 120" role="img" aria-label="Example temperature telemetry placeholder">
                <path d="M 10 98 L 85 90 L 150 64 L 225 48 L 300 50 L 380 32 L 490 35" />
              </svg>
              <p>Actual telemetry is not connected.</p>
            </section>
            <section className="logsPanel mediaPlaceholder" aria-labelledby="media-title">
              <div className="logsPanelHeading"><span className="panelEyebrow">Future run media</span><h2 id="media-title">Camera media</h2></div>
              <div className="cameraPlaceholders"><div>Reactor camera media</div><div>Overview camera media</div></div>
              <p>No recorded media in this frontend draft. Storage and playback are not implemented.</p>
            </section>
          </div>
        </div>
      </div>
    </main>
  );
}

function GuidedDemoNavigation({ activeSection, onNavigate, onExit }: { activeSection: DemoSection; onNavigate: (section: DemoSection) => void; onExit: () => void }) {
  return <nav className="guidedDemoNavigation" aria-label="Guided Demo navigation"><button type="button" aria-current={activeSection === "cockpit" ? "page" : undefined} onClick={() => onNavigate("cockpit")}>Guided Demo</button><button type="button" aria-current={activeSection === "log" ? "page" : undefined} onClick={() => onNavigate("log")}>Demo Log</button><button type="button" onClick={onExit}>Exit demo</button></nav>;
}

function DemoLog({ phases, firstLiquid, secondLiquid, values, onNavigate, onExit }: { phases: string[]; firstLiquid: string; secondLiquid: string; values: { b1Volume: number; b2Volume: number; solventVolume: number; totalVolume: number; ratioB1: number; additionOrder: AdditionOrder; additionSpeed: number; reactorMixing: number; sfMixing: number; simulatedTemperature: string; reactionDuration: string; delayBetweenAdditions: string }; onNavigate: (section: DemoSection) => void; onExit: () => void }) {
  const [technicalOpen, setTechnicalOpen] = useState(false);
  const humanEvents = [["09:20:00", "Demo configuration confirmed"], ["09:20:08", "UI preview started"], ["09:20:24", "S aspiration completed"], ["09:20:39", "S dispense to Reactor completed"], ["09:21:02", `${firstLiquid} aspiration completed`], ["09:21:18", `${firstLiquid} dispense to Reactor completed`], ["09:21:26", "Reactor mixing command changed"], ["09:21:35", "Delay completed"], ["09:22:04", `${secondLiquid} dispense to Reactor completed`], ["09:22:12", "Reaction hold started"], ["09:22:20", "Simulated temperature changed"], ["09:32:24", "Reactor contents aspiration into P2 completed"], ["09:32:43", "P2 dispense into SF completed"], ["09:32:51", "SF mixing command changed"], ["09:33:20", "Demo completed"]];
  const technicalEvents = [["09:20:08", "Command accepted"], ["09:20:09", "Operation started"], ["09:20:24", "Operation reported complete"], ["09:21:26", "Control update accepted"], ["09:21:34", "Example timeout"], ["09:21:35", "Example fault"]];
  const changes = [["09:21:26", "Reactor mixing command", "50%", "65%", `Dispense ${firstLiquid} to Reactor`], ["09:21:58", "Addition speed command", "40%", "55%", `Dispense ${secondLiquid} to Reactor`], ["09:22:20", "Simulated temperature", "25 °C", "35 °C", "Reaction hold"], ["09:32:51", "SF mixing command", "40%", "55%", "SF mixing"]];
  const summary = [["Status", "Reported completion"], ["Started", "09:20:00"], ["Finished", "09:33:20"], ["Duration", "13 min 20 s"], ["B1 configured volume", `${values.b1Volume} ml`], ["B2 configured volume", `${values.b2Volume} ml`], ["S configured volume", `${values.solventVolume} ml`], ["Total configured volume", `${values.totalVolume} ml`], ["B1:B2 volume ratio", `${values.ratioB1}:${100 - values.ratioB1}`], ["Addition order", values.additionOrder], ["Initial addition speed", `${values.additionSpeed}% commanded level`], ["Initial Reactor mixing", `${values.reactorMixing}% commanded level`], ["Initial SF mixing", `${values.sfMixing}% commanded level`], ["Simulated temperature", `${values.simulatedTemperature} °C`], ["Reaction duration", `${values.reactionDuration} min`], ["Delay between additions", `${values.delayBetweenAdditions} s`]];

  return <main className="appShell guidedDemoShell demoLogShell"><header className="guidedDemoHeader"><div><div className="guidedDemoTitleRow"><div className="brand">Demo Log</div><span>Example data — no backend storage</span></div><p>Configured values, run events, and recorded demo activity</p></div><GuidedDemoNavigation activeSection="log" onNavigate={onNavigate} onExit={onExit} /></header><p className="demoLogDataNotice">All values and events below are example frontend data. Configured volumes are not measured or confirmed delivered volumes.</p><section className="demoLogPanel demoLogSummary"><div className="demoSectionHeading"><span>Selected example demo run</span><h2>Run summary</h2></div><dl>{summary.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl></section><div className="demoLogMainGrid"><section className="demoLogPanel demoLogTimeline"><div className="demoSectionHeading"><span>Example events</span><h2>Human event timeline</h2></div><ol>{humanEvents.map(([time, event]) => <li key={`${time}-${event}`}><time>{time}</time><span>{event}</span></li>)}</ol></section><aside className="demoLogSideColumn"><section className="demoLogPanel"><div className="demoSectionHeading"><span>Example command updates</span><h2>Control-change history</h2></div><div className="demoControlHistory">{changes.map(([time, control, previous, next, phase]) => <div key={`${time}-${control}`}><time>{time}</time><strong>{control}</strong><span>{previous} → {next}</span><small>{phase} · Command only; physical response not confirmed</small></div>)}</div></section><section className="demoLogPanel"><button className="demoTechnicalToggle" type="button" aria-expanded={technicalOpen} onClick={() => setTechnicalOpen((open) => !open)}>Show technical details <span>{technicalOpen ? "Hide" : "Expand"}</span></button>{technicalOpen && <ol className="demoTechnicalEvents">{technicalEvents.map(([time, event]) => <li key={`${time}-${event}`}><time>{time}</time><span>{event}</span></li>)}</ol>}</section></aside></div><section className="demoLogPanel"><div className="demoSectionHeading"><span>Example phase record</span><h2>Phase progress</h2></div><ol className="demoLogPhases">{phases.map((phase, index) => <li className={index < phases.length - 1 ? "complete" : "current"} key={phase}><span>{index + 1}</span><small>{phase}</small></li>)}</ol></section><section className="demoLogMedia" aria-label="Future camera media"><div><strong>Reactor camera media</strong><span>No recorded media in frontend draft</span><small>Storage and playback not implemented</small></div><div><strong>Overview camera media</strong><span>No recorded media in frontend draft</span><small>Storage and playback not implemented</small></div></section></main>;
}

function GuidedDemo({ onExit }: { onExit: () => void }) {
  const [demoSection, setDemoSection] = useState<DemoSection>("cockpit");
  const [stage, setStage] = useState<DemoStage>("configure");
  const [ratioB1, setRatioB1] = useState(40);
  const [totalVolume, setTotalVolume] = useState("10");
  const [combinedVolume, setCombinedVolume] = useState("4");
  const [additionOrder, setAdditionOrder] = useState<AdditionOrder>("B1 then B2");
  const [additionSpeed, setAdditionSpeed] = useState(50);
  const [reactorMixing, setReactorMixing] = useState(60);
  const [sfMixing, setSfMixing] = useState(40);
  const [simulatedTemperature, setSimulatedTemperature] = useState("25");
  const [reactionDuration, setReactionDuration] = useState("10");
  const [delayBetweenAdditions, setDelayBetweenAdditions] = useState("5");
  const [additionalOpen, setAdditionalOpen] = useState(false);
  const [previewStarted, setPreviewStarted] = useState(false);
  const [phaseIndex, setPhaseIndex] = useState(0);
  const [reactorPrimary, setReactorPrimary] = useState(true);

  const total = Number(totalVolume);
  const combined = Number(combinedVolume);
  const volumesValid = Number.isFinite(total) && total > 0 && Number.isFinite(combined) && combined > 0 && combined <= total;
  const b1Volume = volumesValid ? combined * (ratioB1 / 100) : 0;
  const b2Volume = volumesValid ? combined - b1Volume : 0;
  const solventVolume = volumesValid ? Math.max(0, total - combined) : 0;
  const firstLiquid = additionOrder === "B1 then B2" ? "B1" : "B2";
  const secondLiquid = firstLiquid === "B1" ? "B2" : "B1";
  const formatVolume = (value: number) => Number(value.toFixed(2));
  const speedLabel = additionSpeed < 34 ? "Slow" : additionSpeed < 67 ? "Medium" : "Fast";
  const phases = [
    "Ready",
    "Aspirate S into P1",
    "Dispense S to Reactor",
    `Aspirate ${firstLiquid} into P1`,
    `Dispense ${firstLiquid} to Reactor`,
    "Delay between additions",
    `Aspirate ${secondLiquid} into P1`,
    `Dispense ${secondLiquid} to Reactor`,
    "Reaction hold",
    "Aspirate Reactor contents into P2",
    "Dispense P2 into SF",
    "SF mixing",
    "Completed",
  ];
  const isAdditionPhase = [2, 4, 7].includes(phaseIndex);
  const isReactorPhase = phaseIndex >= 1 && phaseIndex <= 8;
  const isReactionHold = phaseIndex === 8;
  const isDelayPhase = phaseIndex === 5;
  const isSfMixingPhase = phaseIndex === 11;
  const demoActiveSegments = (() => {
    if (phaseIndex === 1) return new Set(["s-v6", "v6-v1", "v1-p1"]);
    if (phaseIndex === 2 || phaseIndex === 4 || phaseIndex === 7) return new Set(["v1-p1", "v1-v2", "v2-reactor"]);
    if (phaseIndex === 3 || phaseIndex === 6) {
      const liquid = phaseIndex === 3 ? firstLiquid : secondLiquid;
      return new Set([liquid === "B1" ? "b1-v4" : "b2-v4", "v4-v6", "v6-v1", "v1-p1"]);
    }
    if (phaseIndex === 9) return new Set(["reactor-v3", "v3-p2"]);
    if (phaseIndex === 10) return new Set(["v3-p2", "v3-v7", "v7-sf"]);
    return new Set<string>();
  })();

  const volumeSummary = (
    <div className="demoVolumeSummary" aria-label="Calculated configured volumes">
      <div><span>B1</span><strong>{formatVolume(b1Volume)} ml</strong></div>
      <div><span>B2</span><strong>{formatVolume(b2Volume)} ml</strong></div>
      <div><span>S</span><strong>{formatVolume(solventVolume)} ml</strong></div>
      <div><span>Total</span><strong>{volumesValid ? formatVolume(total) : 0} ml</strong></div>
    </div>
  );

  if (demoSection === "log") {
    return <DemoLog phases={phases} firstLiquid={firstLiquid} secondLiquid={secondLiquid} values={{ b1Volume: formatVolume(b1Volume), b2Volume: formatVolume(b2Volume), solventVolume: formatVolume(solventVolume), totalVolume: volumesValid ? formatVolume(total) : 0, ratioB1, additionOrder, additionSpeed, reactorMixing, sfMixing, simulatedTemperature, reactionDuration, delayBetweenAdditions }} onNavigate={setDemoSection} onExit={onExit} />;
  }

  return (
    <main className="appShell guidedDemoShell">
      <header className="guidedDemoHeader">
        <div><div className="guidedDemoTitleRow"><div className="brand">LabForge Guided Demo</div><span>Frontend preview — no hardware control</span></div><p>Configure one colored-liquid run and preview remote controls</p></div>
        <GuidedDemoNavigation activeSection="cockpit" onNavigate={setDemoSection} onExit={onExit} />
      </header>

      <ol className="demoStageIndicator" aria-label="Guided Demo stages">
        {(["configure", "review", "live"] as DemoStage[]).map((item, index) => <li key={item} className={stage === item ? "active" : ""}><span>{index + 1}</span>{item === "configure" ? "Configure" : item === "review" ? "Review" : "Live control preview"}</li>)}
      </ol>

      <section className="demoCockpitVisuals" aria-label="Persistent process visualization">
        <div className="demoCockpitScheme"><FluidicScheme activeSegments={stage === "live" ? demoActiveSegments : new Set()} /></div>
        <div className="demoPersistentCameras">
          <div className="demoCameraHeader"><span>Camera views</span><button type="button" onClick={() => setReactorPrimary((primary) => !primary)}>Swap cameras</button></div>
          <div className="demoCameraPrimary"><span>{reactorPrimary ? "Reactor camera" : "Overview camera"}</span><strong>Stream not connected</strong><small>No live video in frontend preview</small></div>
          <div className="demoCameraSecondary"><span>{reactorPrimary ? "Overview camera" : "Reactor camera"}</span><strong>Stream not connected</strong><small>No live video in frontend preview</small></div>
        </div>
      </section>

      {stage === "configure" && (
        <div className="demoConfigureLayout demoControlTray">
          <div className="demoSettingsColumn">
            <section className="demoPanel"><div className="demoSectionHeading"><span>Main settings</span><h2>Define the colored-liquid run</h2></div><div className="demoMainSettings">
              <label className="demoRangeField"><span>B1:B2 volume ratio <strong>B1 {ratioB1} : {100 - ratioB1} B2</strong></span><input type="range" min="0" max="100" value={ratioB1} onChange={(event) => setRatioB1(Number(event.target.value))} /></label>
              <label>Total mixture volume<div className="demoInputWithUnit"><input type="number" min="0" step="0.1" value={totalVolume} onChange={(event) => setTotalVolume(event.target.value)} /><span>ml</span></div></label>
              <label>Addition order<select value={additionOrder} onChange={(event) => setAdditionOrder(event.target.value as AdditionOrder)}><option>B1 then B2</option><option>B2 then B1</option></select></label>
              <label>Reaction duration<div className="demoInputWithUnit"><input type="number" min="0" value={reactionDuration} onChange={(event) => setReactionDuration(event.target.value)} /><span>min</span></div></label>
            </div></section>
            <section className="demoPanel"><div className="demoSectionHeading"><span>Process settings</span><h2>Preview control commands</h2></div><div className="demoProcessSettings">
              <label className="demoRangeField"><span>Addition speed command <strong>{speedLabel} · {additionSpeed}%</strong></span><input type="range" min="0" max="100" value={additionSpeed} onChange={(event) => setAdditionSpeed(Number(event.target.value))} /></label>
              <label className="demoRangeField"><span>Reactor mixing command <strong>{reactorMixing}%</strong></span><input type="range" min="0" max="100" value={reactorMixing} onChange={(event) => setReactorMixing(Number(event.target.value))} /></label>
              <label className="demoRangeField"><span>SF mixing command <strong>{sfMixing}%</strong></span><input type="range" min="0" max="100" value={sfMixing} onChange={(event) => setSfMixing(Number(event.target.value))} /></label>
              <label>Simulated target temperature <small>Simulated · Heating disabled</small><div className="demoInputWithUnit"><input type="number" value={simulatedTemperature} onChange={(event) => setSimulatedTemperature(event.target.value)} /><span>°C</span></div></label>
            </div></section>
          </div>
          <section className="demoAdditionalPanel"><button type="button" aria-expanded={additionalOpen} onClick={() => setAdditionalOpen((open) => !open)}>Additional settings <span>{additionalOpen ? "Hide" : "Show"}</span></button>{additionalOpen && <div className="demoAdditionalSettings"><label>Combined B1+B2 volume<div className="demoInputWithUnit"><input type="number" min="0" step="0.1" value={combinedVolume} onChange={(event) => setCombinedVolume(event.target.value)} /><span>ml</span></div></label><label>Delay between additions<div className="demoInputWithUnit"><input type="number" min="0" value={delayBetweenAdditions} onChange={(event) => setDelayBetweenAdditions(event.target.value)} /><span>s</span></div></label></div>}</section>
          <footer className="demoConfigureFooter"><div><span className="demoFooterLabel">Calculated volumes</span>{volumeSummary}{!volumesValid && <p className="demoValidationMessage">Combined B1+B2 volume must be greater than zero and no larger than total volume.</p>}</div><div className="demoScopeStrip" aria-label="Demo scope"><span>Colored liquids only</span><span>One run</span><span>Heating disabled</span><span>Temperature simulated</span><span>Remote access not implemented</span><span>Local approval not implemented</span></div><button className="demoPrimaryButton" type="button" disabled={!volumesValid} onClick={() => setStage("review")}>Review configured run</button></footer>
        </div>
      )}

      {stage === "review" && (
        <div className="demoReviewLayout demoControlTray"><section className="demoPanel"><div className="demoSectionHeading"><span>Configured volume plan</span><h2>Review one colored-liquid run</h2></div>{volumeSummary}<dl className="demoReviewSettings"><div><dt>B1:B2 ratio</dt><dd>{ratioB1}:{100 - ratioB1}</dd></div><div><dt>Addition order</dt><dd>{additionOrder}</dd></div><div><dt>Addition speed command</dt><dd>{speedLabel} · {additionSpeed}%</dd></div><div><dt>Reactor mixing command</dt><dd>{reactorMixing}%</dd></div><div><dt>SF mixing command</dt><dd>{sfMixing}%</dd></div><div><dt>Simulated temperature</dt><dd>{simulatedTemperature} °C · Heating disabled</dd></div><div><dt>Reaction duration</dt><dd>{reactionDuration} min</dd></div><div><dt>Delay between additions</dt><dd>{delayBetweenAdditions} s</dd></div></dl></section><section className="demoPanel"><div className="demoSectionHeading"><span>Human-readable protocol</span><h2>Preview timeline</h2></div><ol className="demoProtocolTimeline"><li>Add S</li><li>Add {firstLiquid}</li><li>Delay {delayBetweenAdditions} s</li><li>Add {secondLiquid}</li><li>Reaction hold · {reactionDuration} min</li><li>Transfer to SF</li><li>SF mixing</li></ol></section><div className="demoReviewActions"><button type="button" onClick={() => setStage("configure")}>Back to settings</button><button className="demoPrimaryButton" type="button" onClick={() => setStage("live")}>Start UI preview</button></div></div>
      )}

      {stage === "live" && (
        <div className="demoLiveLayout demoControlTray">
          <section className="demoLiveStatus demoPanel"><div><span>UI preview · No hardware connected</span><h2>{phases[phaseIndex]}</h2></div><div className="demoPreviewActions"><button type="button" disabled={previewStarted} onClick={() => { setPreviewStarted(true); setPhaseIndex(1); }}>Start preview</button><button type="button" disabled={!previewStarted || phaseIndex === phases.length - 1} onClick={() => setPhaseIndex((current) => Math.min(current + 1, phases.length - 1))}>Next phase</button><button type="button" onClick={() => { setPreviewStarted(false); setPhaseIndex(0); }}>Reset preview</button></div></section>
          <div className="demoPhaseProgress">{phases.map((phase, index) => <div key={phase} className={index === phaseIndex ? "active" : index < phaseIndex ? "complete" : ""}><span>{index + 1}</span><small>{phase}</small></div>)}</div>
          <div className="demoLiveLower"><section className="demoPanel"><div className="demoSectionHeading"><span>Real-time control preview</span><h2>Phase-aware local controls</h2></div><div className="demoLiveControls">
            <label className="demoRangeField"><span>Addition speed <strong>{speedLabel} · {additionSpeed}%</strong></span><input type="range" min="0" max="100" value={additionSpeed} disabled={!isAdditionPhase} onChange={(event) => setAdditionSpeed(Number(event.target.value))} /><small>{isAdditionPhase ? "Editable in this UI preview phase" : "Available during liquid addition phases"}</small></label>
            <label className="demoRangeField"><span>Reactor mixing <strong>{reactorMixing}%</strong></span><input type="range" min="0" max="100" value={reactorMixing} disabled={!isReactorPhase} onChange={(event) => setReactorMixing(Number(event.target.value))} /><small>{isReactorPhase ? "Editable in this UI preview phase" : "Available during reactor-related phases"}</small></label>
            <label className="demoRangeField"><span>SF mixing command <strong>{sfMixing}%</strong></span><input type="range" min="0" max="100" value={sfMixing} disabled={!isSfMixingPhase} onChange={(event) => setSfMixing(Number(event.target.value))} /><small>{isSfMixingPhase ? "Editable in the SF mixing preview phase" : "Available during the SF mixing phase"}</small></label>
            <label>Simulated temperature <small>Heating disabled · Display-only simulation</small><div className="demoInputWithUnit"><input type="number" value={simulatedTemperature} disabled={!isReactionHold} onChange={(event) => setSimulatedTemperature(event.target.value)} /><span>°C</span></div></label>
            <label>Reaction duration / remaining time <small>Static local preview value</small><div className="demoInputWithUnit"><input type="number" min="0" value={reactionDuration} disabled={!isReactionHold} onChange={(event) => setReactionDuration(event.target.value)} /><span>min</span></div></label>
            <label>Delay between additions <small>{isDelayPhase ? "Editable during the delay preview phase" : "Available during the delay phase"}</small><div className="demoInputWithUnit"><input type="number" min="0" value={delayBetweenAdditions} disabled={!isDelayPhase} onChange={(event) => setDelayBetweenAdditions(event.target.value)} /><span>s</span></div></label>
          </div></section><aside className="demoPanel"><div className="demoSectionHeading"><span>Locked fluid plan</span><h2>Current settings</h2></div>{volumeSummary}<p className="demoLockedNote">These values define the fluid plan and cannot be changed after execution begins.</p><dl className="demoReviewSettings compact"><div><dt>B1:B2</dt><dd>{ratioB1}:{100 - ratioB1}</dd></div><div><dt>Addition order</dt><dd>{additionOrder}</dd></div></dl></aside></div>
        </div>
      )}
    </main>
  );
}

function ProtocolBuilder({
  runName,
  preRunChecks,
  steps,
  onRunNameChange,
  onCheckChange,
  onAddStep,
  onStepChange,
  onMoveStep,
  onRemoveStep,
  onNavigate,
}: {
  runName: string;
  preRunChecks: PreRunChecks;
  steps: ProtocolStep[];
  onRunNameChange: (value: string) => void;
  onCheckChange: (key: PreRunCheckKey, checked: boolean) => void;
  onAddStep: (type: ProtocolStepType) => void;
  onStepChange: (step: ProtocolStep) => void;
  onMoveStep: (index: number, direction: -1 | 1) => void;
  onRemoveStep: (id: number) => void;
  onNavigate: (screen: Screen) => void;
}) {
  const doseSteps = steps.filter((step): step is DoseStep => step.type === "Dose");
  const doseOrder = doseSteps
    .map((step) => step.source)
    .filter((source): source is Exclude<DoseSource, ""> => source !== "")
    .join(" → ");
  const configuredVolumes = doseSteps
    .map((step) => step.volume.trim())
    .filter((value) => value !== "")
    .map(Number)
    .filter((value) => Number.isFinite(value) && value > 0);
  const totalVolume = configuredVolumes.reduce((total, volume) => total + volume, 0);
  const totalVolumeLabel =
    configuredVolumes.length === 0
      ? "Not configured"
      : `${Number(totalVolume.toFixed(6))} ml${
          configuredVolumes.length < doseSteps.length ? " (incomplete)" : ""
        }`;
  const reactionHoldRule = steps.find(
    (step): step is ReactionHoldStep => step.type === "Reaction hold" && step.startTimer !== "",
  )?.startTimer;

  return (
    <main className="appShell">
      <header className="topBar protocolBuilderTopBar">
        <div>
          <div className="protocolBuilderHeadingRow">
            <div className="brand">Protocol Builder</div>
            <div className="experimentalLabel">Experimental</div>
          </div>
          <div className="subBrand">Define one P1 screening run</div>
        </div>

        <div className="protocolBuilderHeaderActions">
          <TopNavigation activeScreen="protocolBuilder" onNavigate={onNavigate} />
          <div className="draftNotice">Draft only — no hardware execution</div>
        </div>
      </header>

      <div className="protocolBuilderLayout">
        <div className="protocolBuilderMainColumn">
          <section className="protocolBuilderCard" aria-labelledby="run-setup-title">
            <div className="protocolCardHeading">
              <h2 id="run-setup-title">Run setup</h2>
              <p>Basic context for this experimental P1 screening draft.</p>
            </div>
            <label className="protocolField" htmlFor="run-name">
              <span>Run name</span>
              <input
                id="run-name"
                type="text"
                value={runName}
                placeholder="Untitled screening run"
                onChange={(event) => onRunNameChange(event.target.value)}
              />
            </label>
            <div className="seriesContext" aria-label="Series context">
              <div className="protocolSectionLabel">Series context</div>
              <div className="seriesContextGrid">
                {(["B1", "B2", "S"] as const).map((source) => (
                  <div key={source}>
                    <strong>{source}</strong>
                    <span>Not configured</span>
                  </div>
                ))}
              </div>
            </div>
          </section>

          <section className="protocolBuilderCard" aria-labelledby="pre-run-checks-title">
            <div className="protocolCardHeading">
              <h2 id="pre-run-checks-title">Pre-run checks</h2>
              <p>Some checks will later be confirmed by the system and others by the chemist.</p>
            </div>
            <div className="preRunCheckGrid">
              {(
                [
                  ["sourcesAvailable", "Sources available"],
                  ["p1AndValvesHomed", "P1 and valves homed"],
                  ["reactorEmptyAndClean", "Reactor empty and clean"],
                  ["wasteCapacityAvailable", "Waste capacity available"],
                ] as const
              ).map(([key, label]) => (
                <label key={key} className="preRunCheck">
                  <input
                    type="checkbox"
                    checked={preRunChecks[key]}
                    onChange={(event) => onCheckChange(key, event.target.checked)}
                  />
                  <span>{label}</span>
                </label>
              ))}
            </div>
          </section>

          <section className="protocolBuilderCard" aria-labelledby="protocol-steps-title">
            <div className="protocolCardHeading">
              <h2 id="protocol-steps-title">Protocol steps</h2>
              <p>High-level draft actions only. No physical routes or hardware commands are generated.</p>
            </div>
            <div className="addStepControls" aria-label="Add protocol step">
              {(["Dose", "Wait", "Set mixing", "Set temperature", "Reaction hold"] as const).map(
                (type) => (
                  <button key={type} type="button" onClick={() => onAddStep(type)}>
                    + {type}
                  </button>
                ),
              )}
            </div>
            <div className="protocolStepList">
              {steps.map((step, index) => (
                <ProtocolStepCard
                  key={step.id}
                  step={step}
                  index={index}
                  stepCount={steps.length}
                  onChange={onStepChange}
                  onMove={onMoveStep}
                  onRemove={onRemoveStep}
                />
              ))}
            </div>
          </section>
        </div>

        <aside className="protocolBuilderSidebar" aria-label="Run summary and assumptions">
          <section className="protocolBuilderCard">
            <div className="protocolCardHeading">
              <h2>Run summary</h2>
            </div>
            <dl className="runSummaryList">
              <div>
                <dt>Run name</dt>
                <dd>{runName.trim() || "Not configured"}</dd>
              </div>
              <div>
                <dt>Step count</dt>
                <dd>{steps.length}</dd>
              </div>
              <div>
                <dt>Dose order</dt>
                <dd>{doseOrder || "Not configured"}</dd>
              </div>
              <div>
                <dt>Requested total volume</dt>
                <dd>{totalVolumeLabel}</dd>
              </div>
              <div>
                <dt>Reaction hold rule</dt>
                <dd>{reactionHoldRule || "Not configured"}</dd>
              </div>
              <div>
                <dt>Configuration status</dt>
                <dd><span className="incompleteStatus">Incomplete</span></dd>
              </div>
            </dl>
          </section>

          <section className="protocolBuilderCard assumptionsCard">
            <div className="protocolCardHeading">
              <h2>Assumptions</h2>
              <p>Explicit limitations of this experimental draft.</p>
            </div>
            <ul>
              <li>Dead volumes are not measured</li>
              <li>Prime and purge volumes are not validated</li>
              <li>Aspiration and dispense rate units are not finalized</li>
              <li>Delivered volume is not independently measured</li>
              <li>This draft cannot execute hardware</li>
            </ul>
          </section>
        </aside>
      </div>
    </main>
  );
}

export default function App() {
  const [activeScreen, setActiveScreen] = useState<Screen>("dashboard");
  const [runName, setRunName] = useState("");
  const [preRunChecks, setPreRunChecks] = useState<PreRunChecks>({
    sourcesAvailable: false,
    p1AndValvesHomed: false,
    reactorEmptyAndClean: false,
    wasteCapacityAvailable: false,
  });
  const [protocolSteps, setProtocolSteps] = useState<ProtocolStep[]>(initialProtocolSteps);

  const addProtocolStep = (type: ProtocolStepType) => {
    setProtocolSteps((currentSteps) => {
      const nextStepId = Math.max(0, ...currentSteps.map((step) => step.id)) + 1;
      return [...currentSteps, createProtocolStep(type, nextStepId)];
    });
  };

  const moveProtocolStep = (index: number, direction: -1 | 1) => {
    setProtocolSteps((currentSteps) => {
      const targetIndex = index + direction;

      if (targetIndex < 0 || targetIndex >= currentSteps.length) {
        return currentSteps;
      }

      const reorderedSteps = [...currentSteps];
      [reorderedSteps[index], reorderedSteps[targetIndex]] = [
        reorderedSteps[targetIndex],
        reorderedSteps[index],
      ];
      return reorderedSteps;
    });
  };

  if (activeScreen === "protocolBuilder") {
    return (
      <ProtocolBuilder
        runName={runName}
        preRunChecks={preRunChecks}
        steps={protocolSteps}
        onRunNameChange={setRunName}
        onCheckChange={(key, checked) =>
          setPreRunChecks((currentChecks) => ({ ...currentChecks, [key]: checked }))
        }
        onAddStep={addProtocolStep}
        onStepChange={(updatedStep) =>
          setProtocolSteps((currentSteps) =>
            currentSteps.map((step) => (step.id === updatedStep.id ? updatedStep : step)),
          )
        }
        onMoveStep={moveProtocolStep}
        onRemoveStep={(id) =>
          setProtocolSteps((currentSteps) => currentSteps.filter((step) => step.id !== id))
        }
        onNavigate={setActiveScreen}
      />
    );
  }

  if (activeScreen === "logs") {
    return <LogsScreen onNavigate={setActiveScreen} />;
  }

  if (activeScreen === "service") {
    return <ServiceScreen onNavigate={setActiveScreen} />;
  }

  if (activeScreen === "guidedDemo") {
    return <GuidedDemo onExit={() => setActiveScreen("dashboard")} />;
  }

  return (
    <main className="appShell">
      <header className="topBar">
        <div>
          <div className="brand">LABFORGE SCHEME DRAFT</div>
          <div className="subBrand">
            Ventil verzija 2, portovi označeni, aktivna ruta: B1 → P1
          </div>
        </div>

        <div className="topBarActions">
          <button className="guidedDemoLaunch" type="button" onClick={() => setActiveScreen("guidedDemo")}>Open Guided Demo</button>
          <TopNavigation activeScreen="dashboard" onNavigate={setActiveScreen} />
          <div className="statusPill">SCHEME PREVIEW</div>
        </div>
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
          <FluidicScheme />
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
