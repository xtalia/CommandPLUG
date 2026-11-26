import { host, useValue } from "@hermes/plugin-sdk";
import { useEffect, useState } from "react";
import { jsx } from "react/jsx-runtime";

const SENTINEL = "CommandPLUG: active";
const COMMAND = "commandplug";
const POLL_MS = 20000;
const TIMEOUT_MS = 5000;


function isActive(reply) {
  return Boolean(reply) && reply.type === "plugin" && reply.output === SENTINEL;
}

async function readCli(profile) {
  try {
    const reply = await host.request(
      "command.dispatch",
      { name: COMMAND, arg: "dependencies", profile },
      TIMEOUT_MS
    );
    if (!reply || reply.type !== "plugin" || typeof reply.output !== "string") return "unknown";
    const payload = JSON.parse(reply.output);
    const state = payload && payload.commandcode;
    return state === "found" || state === "missing" ? state : "unknown";
  } catch {
    return "unknown";
  }
}

const CHIP = {
  display: "inline-flex",
  alignItems: "center",
  gap: "5px",
  padding: "0 4px",
  font: "inherit",
  color: "var(--ui-text-secondary)",
  whiteSpace: "nowrap",
  cursor: "default",
};

const PHASES = {
  active: { label: "active", dot: "var(--ui-green)" },
  inactive: { label: "unconfirmed", dot: "var(--ui-yellow)" },
  pending: { label: "checking", dot: "var(--ui-yellow)" },
  offline: { label: "offline", dot: "var(--ui-text-quaternary)" },
};

function StatusChip() {
  const gateway = useValue(host.state.gateway);
  const profile = useValue(host.state.profile);
  const connectionId = useValue(host.state.connectionId);
  return jsx(StatusProbe, { open: gateway === "open", profile }, JSON.stringify([gateway, profile, connectionId]));
}

function StatusProbe({ open, profile }) {
  const [phase, setPhase] = useState(open ? "pending" : "offline");
  const [cli, setCli] = useState("unknown");

  useEffect(() => {
    let cancelled = false;

    if (!open) {
      setCli("unknown");
      setPhase("offline");
      return () => {
        cancelled = true;
      };
    }

    setPhase("pending");

    const check = async () => {
      try {
        const reply = await host.request(
          "command.dispatch",
          { name: COMMAND, arg: "status", profile },
          TIMEOUT_MS
        );
        if (cancelled) return;
        if (!isActive(reply)) {
          setPhase("inactive");
          return;
        }
        setPhase("active");
        const state = await readCli(profile);
        if (cancelled) return;
        setCli(state);
      } catch {
        if (cancelled) return;
        setPhase("inactive");
      }
    };

    check();
    const timer = setInterval(check, POLL_MS);

    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [open, profile]);

  const tone = PHASES[phase] || PHASES.offline;
  const cliLabel = cli === "found" || cli === "missing" ? cli : "unknown";
  const chipText =
    phase === "active"
      ? "CommandPLUG · CLI " + cliLabel
      : SENTINEL.replace("active", tone.label);
  const accessibleLabel =
    "CommandPLUG status: " +
    tone.label +
    (phase === "active" ? ", CLI " + cliLabel : "") +
    (!open ? " (gateway closed)" : profile ? " (profile " + profile + ")" : "");

  return jsx("span", {
    role: "status",
    "aria-live": "polite",
    "aria-atomic": "true",
    "aria-label": accessibleLabel,
    title: accessibleLabel,
    "data-area": "statusBar.right",
    "data-plugin": "tool-harness",
    style: CHIP,
    children: [
      jsx("span", {
        key: "dot",
        "aria-hidden": "true",
        style: {
          width: "0.5em",
          height: "0.5em",
          borderRadius: "50%",
          backgroundColor: tone.dot,
          display: "inline-block",
        },
      }),
      jsx("span", { key: "text", children: chipText }),
    ],
  });
}

export function register(ctx) {
  ctx.register({
    id: "tool-harness",
    area: "statusBar.right",
    order: 50,
    render: () => jsx(StatusChip, {}),
  });
}

export default {
  id: "tool-harness",
  name: "CommandPLUG",
  register,
};
