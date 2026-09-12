import {
  useEffect,
  useRef,
  useState,
  type CSSProperties,
  type MouseEvent,
} from "react";
import { enterBackend, scanVenue, type ScanResult } from "../backend/handoff";
import { useStore } from "../state/store";

type Phase = "idle" | "ready" | "scanning" | "found" | "entering" | "error";

const HOLD_MS = 1500;
const TAG_STAGGER_MS = 260;
const MONO = "11px var(--sk-font-mono)";

/** Deterministic spread of object tags around the frame, biased to the lower half. */
function tagPosition(i: number, n: number) {
  const side = i % 2 === 0 ? 8 : 64;
  const x = side + ((i * 61.8 + 12) % 20);
  const row =
    n > 1 ? Math.floor(i / 2) / Math.max(1, Math.ceil(n / 2) - 1) : 0.5;
  const y = 26 + row * 50 + ((i * 37) % 7);
  return { left: `${x}%`, top: `${y}%` };
}

export function Landing() {
  const goto = useStore((s) => s.goto);
  const venuePhoto = useStore((s) => s.venuePhoto);
  const setVenuePhoto = useStore((s) => s.setVenuePhoto);
  const logInteraction = useStore((s) => s.logInteraction);
  const pushEvent = useStore((s) => s.pushEvent);
  const inputRef = useRef<HTMLInputElement>(null);
  const [photoUrl, setPhotoUrl] = useState<string | null>(null);
  const [phase, setPhase] = useState<Phase>("idle");
  const [error, setError] = useState("");
  const [scan, setScan] = useState<ScanResult | null>(null);
  const [revealed, setRevealed] = useState(0);
  const [dragOver, setDragOver] = useState(false);
  const [tilt, setTilt] = useState({ x: 0, y: 0 });
  const [hold, setHold] = useState(0);
  const holdRaf = useRef(0);
  const holdStart = useRef(0);

  useEffect(() => {
    if (!venuePhoto) {
      setPhotoUrl(null);
      setPhase("idle");
      return;
    }
    const url = URL.createObjectURL(venuePhoto);
    setPhotoUrl(url);
    setPhase("ready");
    return () => URL.revokeObjectURL(url);
  }, [venuePhoto]);

  // object tags pop in one by one after the scan returns
  useEffect(() => {
    if (phase !== "found" || !scan) return;
    setRevealed(0);
    let i = 0;
    const id = window.setInterval(() => {
      i += 1;
      setRevealed(i);
      if (i >= scan.objects.length) window.clearInterval(id);
    }, TAG_STAGGER_MS);
    return () => window.clearInterval(id);
  }, [phase, scan]);

  const acceptFile = (file: File | undefined) => {
    if (!file || !file.type.startsWith("image/")) return;
    setError("");
    setScan(null);
    setVenuePhoto(file);
  };

  const startScan = async () => {
    if (!venuePhoto || phase === "scanning") return;
    setPhase("scanning");
    setError("");
    logInteraction("enter_backend", {
      bytes: venuePhoto.size,
      name: (venuePhoto as File).name ?? "photo",
    });
    try {
      const [result] = await Promise.all([
        scanVenue(venuePhoto),
        new Promise((r) => window.setTimeout(r, 2200)), // let the sweep read as a real scan
      ]);
      setScan(result);
      setPhase("found");
      pushEvent(`Found ${result.objects.length} objects in your venue`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setPhase("error");
    }
  };

  const beginHold = () => {
    if (phase !== "found") return;
    holdStart.current = performance.now();
    const tick = () => {
      const p = Math.min(1, (performance.now() - holdStart.current) / HOLD_MS);
      setHold(p);
      if (p >= 1) {
        setPhase("entering");
        pushEvent("Robot awake — entering your venue");
        window.setTimeout(enterBackend, 1100);
        return;
      }
      holdRaf.current = requestAnimationFrame(tick);
    };
    holdRaf.current = requestAnimationFrame(tick);
  };
  const endHold = () => {
    cancelAnimationFrame(holdRaf.current);
    if (phase === "found") setHold(0);
  };

  const onMove = (e: MouseEvent) => {
    const nx = e.clientX / window.innerWidth - 0.5;
    const ny = e.clientY / window.innerHeight - 0.5;
    setTilt({ x: ny * -4, y: nx * 6 });
  };

  const objects = scan?.objects ?? [];
  const immersive = phase !== "idle";
  const ring = 2 * Math.PI * 34;

  return (
    <div
      onMouseMove={onMove}
      onDragOver={(e) => {
        e.preventDefault();
        setDragOver(true);
      }}
      onDragLeave={() => setDragOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragOver(false);
        acceptFile(e.dataTransfer.files?.[0]);
      }}
      style={{ position: "relative", height: "100%", overflow: "hidden" }}
    >
      {/* immersive photo layer: develops on upload, tilts with the cursor */}
      {photoUrl && (
        <div
          key={photoUrl}
          style={{
            position: "absolute",
            inset: "-4%",
            backgroundImage: `url(${photoUrl})`,
            backgroundSize: "cover",
            backgroundPosition: "center",
            animation: "sk-develop 2.2s var(--sk-ease) both",
            transform: `perspective(1200px) rotateX(${tilt.x}deg) rotateY(${tilt.y}deg)`,
            transition: "transform 600ms var(--sk-ease)",
            willChange: "transform",
          }}
        />
      )}
      {immersive && (
        <div
          style={{
            position: "absolute",
            inset: 0,
            background:
              "radial-gradient(ellipse 60% 55% at 50% 55%, rgba(20,17,13,0.55), rgba(20,17,13,0.15) 70%, rgba(20,17,13,0.6))",
          }}
        />
      )}

      {/* scan sweep */}
      {phase === "scanning" && (
        <div
          style={{
            position: "absolute",
            top: 0,
            bottom: 0,
            width: "22vw",
            background:
              "linear-gradient(90deg, transparent, rgba(242,198,109,0.05) 30%, rgba(255,236,190,0.55) 50%, rgba(242,198,109,0.05) 70%, transparent)",
            mixBlendMode: "screen",
            animation: "sk-sweep 1.8s linear infinite",
            pointerEvents: "none",
          }}
        />
      )}

      {/* detected object tags */}
      {(phase === "found" || phase === "entering") &&
        objects.slice(0, revealed).map((o, i) => (
          <div
            key={o.id || i}
            style={{ position: "absolute", ...tagPosition(i, objects.length) }}
          >
            <span
              style={{
                position: "absolute",
                width: 14,
                height: 14,
                borderRadius: "50%",
                border: "1px solid var(--sk-cyan)",
                animation: "sk-ping 1.6s var(--sk-ease) infinite",
              }}
            />
            <span
              style={{
                position: "absolute",
                width: 8,
                height: 8,
                borderRadius: "50%",
                background: "var(--sk-cyan)",
                boxShadow: "var(--sk-glow-cyan)",
                transform: "translate(-50%, -50%)",
              }}
            />
            <div
              className="sk-panel"
              style={{
                position: "absolute",
                left: 14,
                top: -14,
                whiteSpace: "nowrap",
                padding: "5px 8px",
                font: MONO,
                color: "var(--sk-text)",
                animation: "sk-rise 420ms var(--sk-ease) both",
              }}
            >
              {o.label}
              <span style={{ color: "var(--sk-text-dim)" }}>
                {o.material ? ` · ${o.material}` : ""} ·{" "}
                {Math.round(o.confidence * 100)}%
              </span>
            </div>
          </div>
        ))}

      {/* iris close into the robot's eyes */}
      {phase === "entering" && (
        <div
          style={{
            position: "absolute",
            left: "50%",
            top: "50%",
            borderRadius: "50%",
            boxShadow: "0 0 40px 300vmax var(--sk-void)",
            animation: "sk-iris-close 1s var(--sk-ease) 150ms both",
            zIndex: 5,
            pointerEvents: "none",
          }}
        />
      )}

      <input
        ref={inputRef}
        type="file"
        accept="image/*"
        style={{ display: "none" }}
        onChange={(e) => acceptFile(e.target.files?.[0])}
      />

      {/* copy + controls */}
      <div
        style={{
          position: "relative",
          height: "100%",
          display: "grid",
          placeItems: "center",
          textAlign: "center",
          padding: 24,
          zIndex: 2,
        }}
      >
        <div style={{ maxWidth: 620 }}>
          <div
            style={{
              font: "12px var(--sk-font-mono)",
              letterSpacing: 6,
              color: "var(--sk-cyan)",
              animation: "sk-breathe 3.4s var(--sk-ease) infinite",
            }}
          >
            SKOPOS
          </div>

          {phase === "idle" && (
            <>
              <h1 style={h1}>
                Define how your robots behave in your venue — and keep it true
                when the floor moves.
              </h1>
              <p style={lede}>
                Upload a photo of your space, then play inside it — every table
                you move and route you pick teaches Skopos how you like your
                robots to work.
              </p>
              <button
                className="sk-panel"
                onClick={() => inputRef.current?.click()}
                style={{
                  ...pill,
                  transform: dragOver ? "scale(1.06)" : undefined,
                  borderColor: dragOver ? "var(--sk-cyan)" : undefined,
                  boxShadow: dragOver ? "var(--sk-glow-cyan)" : undefined,
                }}
              >
                {dragOver
                  ? "Drop it — we build your world from it"
                  : "Upload a photo of your venue"}
              </button>
              <div style={hint}>
                Step 1 — drop or upload a photo of your physical venue.
              </div>
            </>
          )}

          {phase === "ready" && (
            <div
              style={{ animation: "sk-rise 900ms var(--sk-ease) 1.4s both" }}
            >
              <h1 style={h1}>
                This is your venue. Let’s wake the robot inside it.
              </h1>
              <p style={lede}>
                We’ll scan the room for the things your robot will work around,
                then hand you its eyes.
              </p>
              <button onClick={startScan} style={cta}>
                Scan my venue
              </button>
              <div style={hint}>
                <button onClick={() => inputRef.current?.click()} style={link}>
                  use a different photo
                </button>
              </div>
            </div>
          )}

          {phase === "scanning" && (
            <div style={{ animation: "sk-rise 500ms var(--sk-ease) both" }}>
              <h1 style={h1}>Reading the room…</h1>
              <p style={lede}>
                Surfaces, furniture, hazards — everything the robot must
                respect.
              </p>
            </div>
          )}

          {(phase === "found" || phase === "entering") && (
            <div style={{ animation: "sk-rise 500ms var(--sk-ease) both" }}>
              <h1 style={h1}>
                {phase === "entering"
                  ? "Opening the robot’s eyes…"
                  : `${revealed} object${revealed === 1 ? "" : "s"} mapped. Now become the robot.`}
              </h1>
              <p style={lede}>
                Hold to wake it. From here on you see, move and decide as the
                robot does.
              </p>
              <button
                onPointerDown={beginHold}
                onPointerUp={endHold}
                onPointerLeave={endHold}
                onPointerCancel={endHold}
                onKeyDown={(e) => {
                  if ((e.key === " " || e.key === "Enter") && !e.repeat)
                    beginHold();
                }}
                onKeyUp={endHold}
                disabled={phase === "entering"}
                aria-label="Hold to wake the robot"
                style={{
                  position: "relative",
                  width: 96,
                  height: 96,
                  borderRadius: "50%",
                  border: 0,
                  background: `color-mix(in srgb, var(--sk-cyan) ${12 + hold * 40}%, transparent)`,
                  boxShadow: `0 0 ${18 + hold * 50}px rgba(242,198,109,${0.35 + hold * 0.4})`,
                  cursor: "pointer",
                  animation:
                    hold > 0
                      ? "sk-heartbeat 900ms ease-in-out infinite"
                      : undefined,
                  touchAction: "none",
                  userSelect: "none",
                }}
              >
                <svg
                  viewBox="0 0 80 80"
                  style={{
                    position: "absolute",
                    inset: 4,
                    width: 88,
                    height: 88,
                  }}
                >
                  <circle
                    cx="40"
                    cy="40"
                    r="34"
                    fill="none"
                    stroke="rgba(242,198,109,0.25)"
                    strokeWidth="2"
                  />
                  <circle
                    cx="40"
                    cy="40"
                    r="34"
                    fill="none"
                    stroke="var(--sk-cyan)"
                    strokeWidth="2.5"
                    strokeLinecap="round"
                    strokeDasharray={ring}
                    strokeDashoffset={ring * (1 - hold)}
                    transform="rotate(-90 40 40)"
                  />
                </svg>
                <span
                  style={{
                    font: "22px var(--sk-font-display)",
                    color: "var(--sk-text)",
                  }}
                >
                  {hold >= 1 ? "●" : "◉"}
                </span>
              </button>
              <div style={hint}>
                {hold > 0 ? "keep holding…" : "press and hold"}
              </div>
            </div>
          )}

          {phase === "error" && (
            <div style={{ animation: "sk-rise 500ms var(--sk-ease) both" }}>
              <h1 style={h1}>The scan didn’t come back.</h1>
              <p style={{ ...lede, color: "var(--sk-amber)" }}>{error}</p>
              <div
                style={{
                  display: "flex",
                  gap: 12,
                  justifyContent: "center",
                  alignItems: "center",
                }}
              >
                <button
                  onClick={startScan}
                  style={{
                    ...cta,
                    borderColor: "var(--sk-amber)",
                    color: "var(--sk-amber)",
                  }}
                >
                  Retry
                </button>
                <button onClick={() => goto("setup")} style={link}>
                  Open Setup instead
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

const h1: CSSProperties = {
  fontSize: 44,
  lineHeight: 1.1,
  margin: "18px 0 14px",
  fontWeight: 500,
};
const lede: CSSProperties = {
  color: "var(--sk-text-dim)",
  fontSize: 15,
  marginBottom: 28,
};
const hint: CSSProperties = {
  marginTop: 12,
  font: MONO,
  color: "var(--sk-text-dim)",
};
const pill: CSSProperties = {
  font: "12px var(--sk-font-mono)",
  padding: "10px 16px",
  color: "var(--sk-text)",
  cursor: "pointer",
  transition:
    "transform var(--sk-dur-fast) var(--sk-ease), box-shadow var(--sk-dur-fast)",
};
const cta: CSSProperties = {
  appearance: "none",
  border: "1px solid var(--sk-cyan)",
  background: "color-mix(in srgb, var(--sk-cyan) 12%, transparent)",
  color: "var(--sk-cyan)",
  borderRadius: "var(--sk-radius-md)",
  padding: "12px 22px",
  font: "14px var(--sk-font-display)",
  letterSpacing: 0.5,
  cursor: "pointer",
  boxShadow: "var(--sk-glow-cyan)",
};
const link: CSSProperties = {
  border: 0,
  padding: 0,
  background: "transparent",
  color: "var(--sk-text-dim)",
  font: "inherit",
  textDecoration: "underline",
  cursor: "pointer",
};
