import { useRef, useState, KeyboardEvent, FormEvent } from "react";
import ReactMarkdown from "react-markdown";
import { Send, Loader2 } from "lucide-react";
import type { ToolCall } from "../lib/api";
import { sendChat } from "../lib/api";

export interface ChatTurn {
  role: "user" | "assistant";
  content: string;
  toolCalls?: ToolCall[];
}

interface ChatPanelProps {
  onAssistantAnswer: (answer: string, toolCalls: ToolCall[]) => void;
}

const EXAMPLE_PROMPTS = [
  "Is account 101 currently active?",
  "Which community does account 101 belong to, and what is the open case?",
  "Top 5 cards by fraud count across the warehouse",
  "Show me the circular transfer ring involving 101",
];

export function ChatPanel({ onAssistantAnswer }: ChatPanelProps) {
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const listRef = useRef<HTMLDivElement>(null);

  async function submit(message: string) {
    if (!message.trim() || sending) return;
    setTurns((prev) => [...prev, { role: "user", content: message }]);
    setInput("");
    setSending(true);
    try {
      const resp = await sendChat(message);
      setTurns((prev) => [
        ...prev,
        { role: "assistant", content: resp.answer, toolCalls: resp.tool_calls },
      ]);
      onAssistantAnswer(resp.answer, resp.tool_calls);
    } catch (err) {
      setTurns((prev) => [
        ...prev,
        {
          role: "assistant",
          content: `**Error**: ${(err as Error).message}`,
        },
      ]);
    } finally {
      setSending(false);
      setTimeout(() => {
        listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: "smooth" });
      }, 50);
    }
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    submit(input);
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit(input);
    }
  }

  return (
    <div className="flex h-full flex-col bg-neo-panel border-r border-neo-line">
      <div className="px-5 py-4 border-b border-neo-line">
        <div className="text-sm text-neo-muted uppercase tracking-wider">Graph Intelligence Router</div>
        <div className="text-lg font-semibold">MultiGraphIntel Console</div>
      </div>

      <div ref={listRef} className="flex-1 overflow-y-auto p-5 space-y-4">
        {turns.length === 0 && (
          <div className="space-y-3">
            <p className="text-neo-muted text-sm">
              Ask across Spanner, BigQuery, and Neo4j. The router picks the right substrate automatically.
            </p>
            <div className="flex flex-wrap gap-2">
              {EXAMPLE_PROMPTS.map((p) => (
                <button
                  key={p}
                  onClick={() => submit(p)}
                  className="text-xs rounded-full border border-neo-line px-3 py-1.5 text-neo-ink hover:border-neo-accent hover:text-neo-accent transition-colors"
                >
                  {p}
                </button>
              ))}
            </div>
          </div>
        )}

        {turns.map((turn, idx) => (
          <div key={idx} className="space-y-2">
            {turn.role === "user" ? (
              <div className="flex justify-end">
                <div className="max-w-[85%] rounded-2xl rounded-tr-sm bg-neo-accent/20 border border-neo-accent/40 px-4 py-2 text-sm">
                  {turn.content}
                </div>
              </div>
            ) : (
              <div className="space-y-2">
                <div className="max-w-[95%] rounded-2xl rounded-tl-sm bg-neo-slate border border-neo-line px-4 py-3">
                  <div className="prose prose-sm prose-invert max-w-none">
                    <ReactMarkdown>{turn.content}</ReactMarkdown>
                  </div>
                </div>
                {turn.toolCalls && turn.toolCalls.length > 0 && (
                  <div className="flex flex-wrap gap-1.5 pl-2">
                    {turn.toolCalls.map((tc, i) => (
                      <span
                        key={i}
                        className={`text-[11px] font-mono rounded px-2 py-0.5 border ${substrateStyle(
                          tc.substrate
                        )}`}
                        title={JSON.stringify(tc.arguments)}
                      >
                        {tc.substrate}.{tc.tool}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        ))}
        {sending && (
          <div className="flex items-center gap-2 text-neo-muted text-xs">
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
            Routing your question
          </div>
        )}
      </div>

      <form onSubmit={onSubmit} className="border-t border-neo-line p-3 flex items-end gap-2">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onKeyDown}
          rows={2}
          placeholder="Ask anything across the three graph substrates..."
          className="flex-1 resize-none rounded-lg bg-neo-slate border border-neo-line px-3 py-2 text-sm text-neo-ink placeholder:text-neo-muted focus:outline-none focus:border-neo-accent"
        />
        <button
          type="submit"
          disabled={sending || !input.trim()}
          className="rounded-lg bg-neo-accent px-3 py-2 text-sm font-medium disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-1"
        >
          {sending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
          Send
        </button>
      </form>
    </div>
  );
}

function substrateStyle(substrate: string): string {
  switch (substrate) {
    case "operational":
      return "bg-emerald-500/10 border-emerald-500/40 text-emerald-300";
    case "analytical":
      return "bg-amber-500/10 border-amber-500/40 text-amber-300";
    case "intelligence":
      return "bg-sky-500/10 border-sky-500/40 text-sky-300";
    default:
      return "bg-neo-line/40 border-neo-line text-neo-muted";
  }
}
