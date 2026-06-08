import React, { useMemo } from "react";
import { ArrowLeft, BookOpen, PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { cx } from "../../shared/lib/classNames.js";
import {
  button,
  buttonSecondary,
  emptyPanel,
  errorBanner,
  h1,
  h2,
  headerActions,
  iconButton,
  muted,
  panel,
} from "../../shared/ui/classes.js";
import { usePlayStateQuery, usePlayInputMutation } from "./hooks/usePlayQuery.js";
import CommandComposer from "./components/CommandComposer.jsx";
import PlayLog from "./components/PlayLog.jsx";
import PlaySidePanels from "./components/PlaySidePanels.jsx";

export default function PlayPage({
  worldId,
  setError,
  error,
  sidebarHidden,
  onToggleSidebar,
  onBackToWorld,
}) {
  const { data: playState, isLoading: loading } = usePlayStateQuery({ worldId, enabled: !!worldId });
  const inputMut = usePlayInputMutation({ worldId });
  const inputLoading = inputMut.isPending;

  const world = playState?.world;
  const session = playState?.session;
  const character = playState?.character;
  const currentPlace = playState?.current_place;
  const places = playState?.places ?? [];
  const presentNpcs = playState?.present_npcs ?? [];
  const conversationNpc = playState?.conversation_npc ?? null;
  const messages = playState?.messages ?? [];
  const mode = session?.mode ?? "default";
  const isConversation = mode === "conversation";
  const npcById = useMemo(() => {
    const rows = conversationNpc ? [...presentNpcs, conversationNpc] : presentNpcs;
    return new Map(rows.map((npc) => [npc.id, npc]));
  }, [presentNpcs, conversationNpc]);

  return (
    <main className="min-h-screen min-w-0 bg-[#111111] p-5 text-[#eeeeec] [font-family:Aptos,Bahnschrift,system-ui,sans-serif]">
      <div className="mb-3.5 flex items-center justify-between gap-4 border-b border-[#2e2e2c] pb-3.5">
        <div>
          <h1 className={h1}>{world?.title ?? "Play"}</h1>
          <div className={muted}>
            {loading ? "Loading play state..." : `${currentPlace?.name ?? "Unknown place"} - ${isConversation && conversationNpc ? `Talking to ${conversationNpc.name}` : "Default mode"} - ${character?.name ?? "Kaelen Duskborn"}`}
          </div>
        </div>
        <div className={headerActions}>
          <button className={iconButton} type="button" onClick={onToggleSidebar} title={sidebarHidden ? "Show sidebar" : "Hide sidebar"}>
            {sidebarHidden ? <PanelLeftOpen size={16} /> : <PanelLeftClose size={16} />}
          </button>
          {world?.id ? (
            <button className={cx(button, buttonSecondary)} type="button" onClick={() => onBackToWorld(world.id)}>
              <ArrowLeft size={16} />
              World
            </button>
          ) : null}
        </div>
      </div>

      {error ? <div className={errorBanner}>{error}</div> : null}

      {loading && !playState ? (
        <section className={panel}>
          <div className={emptyPanel}>Loading play state.</div>
        </section>
      ) : (
        <section className="grid items-start gap-3.5 lg:grid-cols-[minmax(0,1fr)_360px]">
          <div className="relative flex min-h-[auto] flex-col overflow-hidden rounded-lg border border-[#2e2e2c] bg-[#171716] lg:min-h-[calc(100vh-110px)] lg:max-h-[calc(100vh-110px)]">
            <div className="relative z-10 flex items-center justify-between gap-4 border-b border-[#2e2e2c] px-4 py-3.5">
              <div>
                <h2 className={h2}>{currentPlace?.name ?? "Unknown place"}</h2>
                <div className={muted}>
                  {[currentPlace?.place_type, currentPlace?.terrain, currentPlace?.danger_level ? `Danger ${currentPlace.danger_level}` : ""].filter(Boolean).join(" - ")}
                </div>
              </div>
              <button className={cx(button, buttonSecondary)} type="button">
                <BookOpen size={16} />
                View Area
              </button>
            </div>
            <p className="relative z-10 m-0 border-b border-[#2e2e2c] px-4 py-3 text-sm leading-[1.55] text-[#d8d3ca]">{currentPlace?.summary ?? "This place has no summary yet."}</p>

            <PlayLog
              messages={messages}
              npcById={npcById}
              characterName={character?.name}
            />

            <CommandComposer
              isConversation={isConversation}
              conversationNpc={conversationNpc}
              places={places}
              presentNpcs={presentNpcs}
              inputLoading={inputLoading}
              onSubmit={(input) => {
                setError("");
                inputMut.mutate(input, {
                  onError: (inputError) => setError(inputError.message),
                });
              }}
            />
          </div>

          <PlaySidePanels character={character} />
        </section>
      )}
    </main>
  );
}
