/**
 * Ink (React) renderer. The initial, feature-rich implementation of the
 * Renderer interface. It is the *only* file allowed to import Ink/React, so it
 * can be replaced wholesale by an in-house renderer later.
 */

import React, { useEffect, useState } from "react";
import { render, Box, Text, useApp, useInput, type Instance } from "ink";
import TextInput from "ink-text-input";
import { EventEmitter } from "node:events";
import type { Renderer } from "./renderer.js";
import type { ToolResult } from "zeno-coding-agent";

type Kind = "user" | "assistant" | "system" | "tool" | "toolResult" | "error";
interface LogEntry {
  kind: Kind;
  text: string;
}

class Store extends EventEmitter {
  log: LogEntry[] = [];
  status = "";
  mode: "idle" | "input" | "permission" = "idle";
  permissionMessage = "";
  streamingIndex: number | null = null;
  resolveInput: ((v: string | null) => void) | null = null;
  resolvePermission: ((v: boolean) => void) | null = null;
  cancelHandler: (() => void) | null = null;

  changed(): void {
    this.emit("change");
  }
}

const ROLE_COLOR: Record<Kind, string> = {
  user: "cyan",
  assistant: "green",
  system: "gray",
  tool: "magenta",
  toolResult: "gray",
  error: "red",
};

function Line({ entry }: { entry: LogEntry }): React.ReactElement {
  const color = ROLE_COLOR[entry.kind];
  const label =
    entry.kind === "user"
      ? "you"
      : entry.kind === "assistant"
        ? "zeno"
        : entry.kind === "tool"
          ? "  ->"
          : entry.kind === "toolResult"
            ? "  ok"
            : entry.kind === "error"
              ? "err"
              : "sys";
  return (
    <Text>
      <Text color={color} bold={entry.kind === "user" || entry.kind === "assistant"}>
        {label}
      </Text>
      <Text>{entry.kind === "tool" || entry.kind === "toolResult" ? " " : ": "}</Text>
      <Text color={entry.kind === "toolResult" || entry.kind === "tool" ? "gray" : undefined}>
        {entry.text}
      </Text>
    </Text>
  );
}

function App({ store }: { store: Store }): React.ReactElement {
  const [, force] = useState(0);
  const [value, setValue] = useState("");
  const { exit } = useApp();

  useEffect(() => {
    const handler = () => force((x) => x + 1);
    store.on("change", handler);
    return () => {
      store.off("change", handler);
    };
  }, [store]);

  useInput((input, key) => {
    if (key.ctrl && input === "c") {
      if (store.streamingIndex !== null && store.cancelHandler) {
        store.cancelHandler();
      } else {
        if (store.resolveInput) store.resolveInput(null);
        exit();
      }
      return;
    }
    if (store.mode === "permission") {
      if (/^y/i.test(input)) {
        store.resolvePermission?.(true);
      } else if (/^n/i.test(input) || key.return || key.escape) {
        store.resolvePermission?.(false);
      }
    }
  });

  return (
    <Box flexDirection="column">
      {store.log.map((entry, i) => (
        <Line key={i} entry={entry} />
      ))}

      {store.mode === "permission" && (
        <Box marginTop={1}>
          <Text color="yellow">permission needed: {store.permissionMessage} allow? [y/N] </Text>
        </Box>
      )}

      {store.mode === "input" && (
        <Box>
          <Text color="cyan">you: </Text>
          <TextInput
            value={value}
            onChange={setValue}
            onSubmit={(submitted: string) => {
              setValue("");
              const resolve = store.resolveInput;
              store.resolveInput = null;
              store.mode = "idle";
              if (submitted.trim()) store.log.push({ kind: "user", text: submitted });
              store.changed();
              resolve?.(submitted);
            }}
          />
        </Box>
      )}

      <Box marginTop={1}>
        <Text color="gray">{store.status}</Text>
      </Box>
    </Box>
  );
}

export class InkRenderer implements Renderer {
  private store = new Store();
  private instance: Instance | null = null;

  start(): void {
    this.instance = render(<App store={this.store} />);
  }

  onCancel(handler: () => void): void {
    this.store.cancelHandler = handler;
  }

  addMessage(role: "user" | "assistant" | "system", text: string): void {
    this.store.log.push({ kind: role, text });
    this.store.changed();
  }

  beginAssistant(): void {
    this.store.log.push({ kind: "assistant", text: "" });
    this.store.streamingIndex = this.store.log.length - 1;
    this.store.changed();
  }

  appendAssistant(text: string): void {
    const i = this.store.streamingIndex;
    if (i !== null && this.store.log[i]) {
      this.store.log[i].text += text;
      this.store.changed();
    }
  }

  endAssistant(): void {
    this.store.streamingIndex = null;
    this.store.changed();
  }

  toolCall(name: string, args: Record<string, unknown>): void {
    this.store.log.push({ kind: "tool", text: `${name} ${JSON.stringify(args)}` });
    this.store.changed();
  }

  toolResult(name: string, result: ToolResult): void {
    const text = result.error
      ? `${name}: ${result.error}`
      : `${name}: ${(result.output ?? "").split("\n")[0] ?? ""}${result.truncated ? " (truncated)" : ""}`;
    this.store.log.push({ kind: result.error ? "error" : "toolResult", text });
    this.store.changed();
  }

  error(message: string): void {
    this.store.log.push({ kind: "error", text: message });
    this.store.changed();
  }

  setStatusLine(text: string): void {
    this.store.status = text;
    this.store.changed();
  }

  requestPermission(message: string): Promise<boolean> {
    return new Promise((resolve) => {
      this.store.permissionMessage = message;
      this.store.mode = "permission";
      this.store.resolvePermission = (v) => {
        this.store.resolvePermission = null;
        this.store.mode = "idle";
        this.store.changed();
        resolve(v);
      };
      this.store.changed();
    });
  }

  prompt(): Promise<string | null> {
    return new Promise((resolve) => {
      this.store.mode = "input";
      this.store.resolveInput = resolve;
      this.store.changed();
    });
  }

  stop(): void {
    this.instance?.unmount();
    this.instance = null;
  }
}
