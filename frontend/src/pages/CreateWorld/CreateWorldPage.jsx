import React from "react";
import CreateWorldForm from "./components/CreateWorldForm.jsx";
import { useCreateWorldPage } from "./hooks/useCreateWorldPage.js";
import { h1 } from "../../shared/ui/classes.js";

export default function CreateWorldPage({ activeModelId, navigateMode, setError, error, onAfterCreate }) {
  const { prompt, setPrompt, creating, createWorld } = useCreateWorldPage({
    activeModelId,
    navigateMode,
    setError,
    onAfterCreate,
  });

  return (
    <main className="min-w-0 bg-[#111111] p-6">
      <div className="mb-[18px] flex items-start justify-between gap-4">
        <h1 className={h1}>Create world</h1>
      </div>
      <CreateWorldForm
        prompt={prompt}
        setPrompt={setPrompt}
        onSubmit={createWorld}
        creating={creating}
        error={error}
      />
    </main>
  );
}
