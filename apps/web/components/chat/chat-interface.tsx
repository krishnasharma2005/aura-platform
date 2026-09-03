"use client";

import * as React from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { AlertTriangle, ArrowDown, ArrowUp, RotateCcw } from "lucide-react";
import type { AgentDefinition } from "@/lib/agents";
import type { ChatMessage, ChatOption } from "@/lib/api-types";
import { api } from "@/lib/api-client";
import { useApprovals } from "@/lib/approvals-context";
import { chipIn, stillVariants } from "@/lib/motion";
import { cn, errorMessage } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { MessageBubble } from "./message-bubble";
import { ThinkingIndicator } from "./thinking-indicator";

let idCounter = 0;
function nextId() {
  idCounter += 1;
  return `local-${Date.now()}-${idCounter}`;
}

/**
 * The conversation surface — where a prospect spends the demo.
 *
 * Three things make it feel alive rather than like a form that posts:
 *   · the user's message lands instantly and the composer clears, before the
 *     network has said anything (optimistic),
 *   · while the agent works, the wait is narrated in the agent's own words
 *     rather than by a spinner,
 *   · the reply is revealed word by word, and whatever the agent reached for
 *     is shown above it before the text arrives.
 *
 * Everything that can fail, fails inline and keeps the conversation on
 * screen. There is no state where this component unmounts the transcript.
 */
export function ChatInterface({ agent }: { agent: AgentDefinition }) {
  const { refresh: refreshApprovals } = useApprovals();
  const reduce = useReducedMotion();

  const [messages, setMessages] = React.useState<ChatMessage[]>([]);
  const [conversationId, setConversationId] = React.useState<string | undefined>(undefined);
  const [input, setInput] = React.useState("");
  const [isSending, setIsSending] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [lastAttempt, setLastAttempt] = React.useState<string | null>(null);
  const [atBottom, setAtBottom] = React.useState(true);
  /**
   * A handful of agents (the Receptionist, for now) run a temporary
   * predefined menu instead of the real AI pipeline — see
   * docs/scope-ledger.md. `menuOptions` holds the latest reply's choices;
   * when it's empty this is an ordinary free-text conversation. `menuNodeId`
   * is which node those options belong to, sent back so the server knows
   * what was picked.
   */
  const [menuOptions, setMenuOptions] = React.useState<ChatOption[]>([]);
  const [menuNodeId, setMenuNodeId] = React.useState<string | null>(null);

  const scrollRef = React.useRef<HTMLDivElement>(null);
  const textareaRef = React.useRef<HTMLTextAreaElement>(null);

  /** Follow new content only while the reader is already at the bottom. */
  const scrollToBottom = React.useCallback(
    (behavior: ScrollBehavior = "smooth") => {
      const el = scrollRef.current;
      if (!el) return;
      el.scrollTo({ top: el.scrollHeight, behavior: reduce ? "auto" : behavior });
    },
    [reduce]
  );

  React.useEffect(() => {
    if (atBottom) scrollToBottom();
  }, [messages, atBottom, scrollToBottom]);

  function handleScroll(e: React.UIEvent<HTMLDivElement>) {
    const el = e.currentTarget;
    setAtBottom(el.scrollHeight - el.scrollTop - el.clientHeight < 80);
  }

  /** The composer grows with the message instead of scrolling inside itself. */
  const autoResize = React.useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 176)}px`;
  }, []);

  /*
   * Also size it before anything is typed, and again when the column changes
   * width. An empty textarea's scrollHeight still accounts for a wrapped
   * placeholder, and these placeholders are a full sentence — on a phone
   * "…as a patient or client would" wrapped to a second line that was cut in
   * half by the one-row height. Sizing on mount and on resize fixes it
   * without shortening the copy, which is doing real work in the demo.
   */
  React.useEffect(() => {
    autoResize();
    window.addEventListener("resize", autoResize);
    return () => window.removeEventListener("resize", autoResize);
  }, [autoResize]);

  async function revealProgressively(fullText: string, messageId: string) {
    if (reduce) {
      setMessages((prev) => prev.map((m) => (m.id === messageId ? { ...m, content: fullText } : m)));
      return;
    }
    const words = fullText.split(" ");
    let shown = "";
    for (let i = 0; i < words.length; i++) {
      shown += (i === 0 ? "" : " ") + words[i];
      const snapshot = shown;
      setMessages((prev) => prev.map((m) => (m.id === messageId ? { ...m, content: snapshot } : m)));
      // eslint-disable-next-line no-await-in-loop
      await new Promise((resolve) => setTimeout(resolve, 18));
    }
  }

  /**
   * Shared by a typed message and a picked menu option — both are "the
   * visitor said something, the agent replied." `displayText` is what shows
   * in the transcript as the user's turn; it differs from `payload.message`
   * for a menu pick, where the wire payload carries `option_id` (not the
   * button's label) but the transcript should still read like a reply.
   */
  async function runTurn(
    payload: { message: string; node_id?: string; option_id?: string },
    displayText: string
  ) {
    if (isSending) return;

    setError(null);
    setLastAttempt(displayText);
    setAtBottom(true);
    setMenuOptions([]);

    const userMessage: ChatMessage = {
      id: nextId(),
      role: "user",
      content: displayText,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    window.requestAnimationFrame(autoResize);
    setIsSending(true);

    try {
      const res = await api.agents.chat(agent.slug, {
        conversation_id: conversationId,
        ...payload,
      });
      setConversationId(res.conversation_id);

      const assistantId = nextId();
      setMessages((prev) => [
        ...prev,
        {
          id: assistantId,
          role: "assistant",
          content: "",
          created_at: new Date().toISOString(),
          tool_calls: res.tool_calls,
          pending_approvals: res.pending_approvals,
        },
      ]);
      await revealProgressively(res.response, assistantId);

      setMenuOptions(res.options ?? []);
      setMenuNodeId(res.node_id ?? null);

      // A queued action also has to appear in the tray in the top bar, so an
      // owner who navigates away still knows the agent is waiting.
      if (res.pending_approvals && res.pending_approvals.length > 0) {
        refreshApprovals();
      }
    } catch (err) {
      setError(
        errorMessage(err, "The agent didn't respond. Check your connection and try again.")
      );
    } finally {
      setIsSending(false);
    }
  }

  function sendMessage(text: string) {
    const trimmed = text.trim();
    if (!trimmed) return;
    return runTurn({ message: trimmed }, trimmed);
  }

  function pickOption(option: ChatOption) {
    return runTurn({ message: "", node_id: menuNodeId ?? undefined, option_id: option.id }, option.label);
  }

  /*
   * Some agents open on a predefined menu rather than a blank composer (see
   * `menuOptions` above). Try once, quietly, on mount: an agent still running
   * the real AI pipeline with no key configured fails the same way it always
   * has, and that failure is swallowed here rather than shown — the ordinary
   * empty state with suggested prompts is exactly the right fallback, not an
   * error banner nobody asked for.
   */
  const greetingAttempted = React.useRef(false);
  React.useEffect(() => {
    if (greetingAttempted.current || messages.length > 0) return;
    greetingAttempted.current = true;

    (async () => {
      try {
        const res = await api.agents.chat(agent.slug, { conversation_id: undefined, message: "" });
        if (!res.options || res.options.length === 0) return;
        setConversationId(res.conversation_id);
        setMessages([
          {
            id: nextId(),
            role: "assistant",
            content: res.response,
            created_at: new Date().toISOString(),
          },
        ]);
        setMenuOptions(res.options);
        setMenuNodeId(res.node_id ?? null);
      } catch {
        // Silent — see comment above.
      }
    })();
  }, [agent.slug, messages.length]);

  const showThinking = isSending && messages[messages.length - 1]?.role === "user";
  const isEmpty = messages.length === 0;
  /*
   * While a predefined menu is on screen the composer is disabled rather than
   * merely ignored: the scripted flow only understands a picked option, so
   * free text would silently bounce the visitor back to the main menu. Better
   * to say the choices are the way forward than to accept input and lose it.
   */
  const menuActive = menuOptions.length > 0;

  return (
    <div className="relative flex h-full flex-col">
      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="relative flex-1 overflow-y-auto scrollbar-thin"
      >
        <div className="mx-auto flex max-w-3xl flex-col gap-5 px-5 py-7 sm:px-6">
          {isEmpty ? (
            <EmptyState agent={agent} onPick={sendMessage} />
          ) : (
            messages.map((m) => (
              <MessageBubble
                key={m.id}
                message={m}
                agentLabel={agent.shortLabel}
                agentName={agent.displayName}
              />
            ))
          )}

          <AnimatePresence>
            {showThinking && <ThinkingIndicator agentLabel={agent.shortLabel} />}
          </AnimatePresence>

          {/*
            Menu choices for an agent running the predefined flow. Rendered
            after the reply they belong to, so the conversation reads
            top-to-bottom: answer, then what you can say next.
          */}
          {menuOptions.length > 0 && !isSending && (
            <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap">
              {menuOptions.map((option, i) => (
                <motion.button
                  key={option.id}
                  type="button"
                  initial={reduce ? { opacity: 0 } : { opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: reduce ? 0 : i * 0.05, duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
                  onClick={() => pickOption(option)}
                  className="press tap-h inline-flex items-center justify-center rounded-full border border-border bg-card px-3.5 py-1.5 text-xs font-medium text-foreground shadow-subtle hover:border-primary/40 hover:bg-primary/[0.05] hover:text-primary"
                >
                  {option.label}
                </motion.button>
              ))}
            </div>
          )}

          {error && (
            <motion.div
              variants={reduce ? stillVariants : chipIn}
              initial="hidden"
              animate="visible"
              role="alert"
              className="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-lg border border-destructive/25 bg-destructive/[0.07] px-3.5 py-3 text-sm text-destructive"
            >
              <span className="flex min-w-0 items-start gap-2">
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" strokeWidth={1.9} />
                <span className="min-w-0">{error}</span>
              </span>
              {lastAttempt && (
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => {
                    setError(null);
                    sendMessage(lastAttempt);
                  }}
                >
                  <RotateCcw className="h-3.5 w-3.5" strokeWidth={2} />
                  Try again
                </Button>
              )}
            </motion.div>
          )}
        </div>
      </div>

      {/* Jump back to the live edge — only offered when you've scrolled off it. */}
      <AnimatePresence>
        {!atBottom && !isEmpty && (
          <motion.button
            initial={reduce ? { opacity: 0 } : { opacity: 0, y: 8, scale: 0.9 }}
            animate={reduce ? { opacity: 1 } : { opacity: 1, y: 0, scale: 1 }}
            exit={reduce ? { opacity: 0 } : { opacity: 0, y: 8, scale: 0.9 }}
            transition={{ type: "spring", stiffness: 480, damping: 34 }}
            onClick={() => {
              setAtBottom(true);
              scrollToBottom();
            }}
            className="press absolute bottom-24 left-1/2 z-10 flex -translate-x-1/2 items-center gap-1.5 rounded-full border border-border bg-card px-3 py-1.5 text-xs font-semibold text-foreground shadow-lifted"
          >
            <ArrowDown className="h-3.5 w-3.5" strokeWidth={2.25} />
            Latest
          </motion.button>
        )}
      </AnimatePresence>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          sendMessage(input);
        }}
        className="shrink-0 border-t border-border bg-background/90 px-5 py-4 backdrop-blur-md sm:px-6"
      >
        <div className="mx-auto max-w-3xl">
          {/*
            The composer is a single nested enclosure rather than a box plus a
            detached button, so it reads as one instrument you type into.
          */}
          <div className="flex items-end gap-2 rounded-xl border border-input bg-card p-1.5 shadow-inset transition-[border-color,box-shadow] duration-200 ease-physical focus-within:border-primary/45 focus-within:ring-2 focus-within:ring-ring/20">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => {
                setInput(e.target.value);
                autoResize();
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  sendMessage(input);
                }
              }}
              rows={1}
              disabled={menuActive}
              placeholder={menuActive ? "Choose one of the options above" : agent.composerPlaceholder}
              aria-label={`Message ${agent.displayName}`}
              className="tap-h max-h-44 min-h-[2.25rem] flex-1 resize-none border-0 bg-transparent px-2.5 py-2 text-sm leading-relaxed text-foreground placeholder:text-subtle focus:outline-none focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-60"
            />
            <Button
              type="submit"
              size="icon"
              className="h-9 w-9 shrink-0 rounded-lg"
              disabled={!input.trim() || isSending || menuActive}
              aria-label="Send message"
            >
              <ArrowUp className="h-4 w-4" strokeWidth={2.5} />
            </Button>
          </div>
          <p className="mt-2 px-1 text-2xs text-muted-foreground">
            {menuActive
              ? "This assistant is answering from a set list of options for now."
              : "Anything that affects a customer, a booking, or your inbox comes back to you for approval first."}
          </p>
        </div>
      </form>
    </div>
  );
}

/**
 * The empty state is the demo's first screen for this agent, so it has one
 * job: get a real question typed. The suggestions are things an actual
 * customer would send, not feature descriptions.
 */
function EmptyState({
  agent,
  onPick,
}: {
  agent: AgentDefinition;
  onPick: (prompt: string) => void;
}) {
  const reduce = useReducedMotion();
  const Icon = agent.icon;

  return (
    <motion.div
      initial={reduce ? { opacity: 0 } : { opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
      className="flex flex-col items-center gap-5 rounded-xl border border-dashed border-border bg-card/60 px-6 py-10 text-center"
    >
      <span className="flex h-12 w-12 items-center justify-center rounded-xl bg-primary/[0.08] text-primary ring-1 ring-inset ring-primary/15">
        <Icon className="h-5 w-5" strokeWidth={1.75} />
      </span>
      <div>
        <h3 className="font-display text-lg font-semibold tracking-[-0.015em] text-foreground">
          {agent.emptyStateTitle}
        </h3>
        <p className="mx-auto mt-2 max-w-md text-sm leading-relaxed text-muted-foreground">
          {agent.emptyStateBody}
        </p>
      </div>
      <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:justify-center">
        {agent.suggestedPrompts.map((prompt, i) => (
          <motion.button
            key={prompt}
            type="button"
            initial={reduce ? { opacity: 0 } : { opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.12 + i * 0.06, duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
            onClick={() => onPick(prompt)}
            className="press tap-h inline-flex items-center justify-center rounded-full border border-border bg-card px-3.5 py-1.5 text-xs font-medium text-foreground shadow-subtle hover:border-primary/40 hover:bg-primary/[0.05] hover:text-primary"
          >
            {prompt}
          </motion.button>
        ))}
      </div>
    </motion.div>
  );
}
