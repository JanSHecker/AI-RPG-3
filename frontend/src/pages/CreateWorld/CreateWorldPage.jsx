import React, { useState } from "react";
import CreateWorldForm from "./components/CreateWorldForm.jsx";
import { useCreateWorldMutation } from "./hooks/useCreateWorldMutation.js";
import { h1 } from "../../shared/ui/classes.js";
import { PATH_JOBS, ROUTE_JOBS } from "../../app/routing.js";

export default function CreateWorldPage({ activeModelId, navigateMode, setError, error, onAfterCreate }) {
  const [prompt, setPrompt] = useState("");
  const createMut = useCreateWorldMutation();
  const creating = createMut.isPending;

  const createWorld = () => {
    setError("");
    createMut.mutate(
      { prompt, modelId: activeModelId },
      {
        onSuccess: () => {
          setPrompt("");
          navigateMode?.(ROUTE_JOBS, PATH_JOBS);
          onAfterCreate?.();
        },
        onError: (createError) => setError(createError.message),
      },
    );
  };

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
