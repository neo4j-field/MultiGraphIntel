import { useState } from "react";
import { ChatPanel } from "./components/ChatPanel";
import { GraphCanvas } from "./components/GraphCanvas";
import { extractEntities, type Entity } from "./lib/extractEntities";

export default function App() {
  const [entities, setEntities] = useState<Entity[]>([]);

  function handleAnswer(answer: string) {
    const found = extractEntities(answer);
    if (found.length > 0) {
      setEntities(found);
    }
  }

  return (
    <div className="h-screen w-screen grid grid-cols-[minmax(380px,460px)_1fr]">
      <ChatPanel onAssistantAnswer={handleAnswer} />
      <GraphCanvas entities={entities} />
    </div>
  );
}
