import React, { useCallback, useEffect, useMemo, useState } from "react";
import Sidebar from "../shared/components/Sidebar.jsx";
import {
  PATH_HOME,
  PATH_JOBS,
  ROUTE_CREATE,
  ROUTE_DETAIL,
  ROUTE_JOBS,
  ROUTE_JOB_DETAIL,
  ROUTE_PLAY,
  isJobsLikePath,
  jobDetailPath,
  playPath,
  routeFromPath,
} from "./routing.js";
import { useModels } from "./hooks/useModels.js";
import { useWorlds } from "./hooks/useWorlds.js";
import CreateWorldPage from "../pages/CreateWorld/CreateWorldPage.jsx";
import GenerationJobsPage from "../pages/GenerationJobs/GenerationJobsPage.jsx";
import GenerationJobDetailPage from "../pages/GenerationJobDetail/GenerationJobDetailPage.jsx";
import WorldDetailPage from "../pages/WorldDetail/WorldDetailPage.jsx";
import PlayPage from "../pages/Play/PlayPage.jsx";

const shellWithSidebar = "grid min-h-screen min-w-80 bg-[#111111] text-[#eeeeec] [color-scheme:dark] [font-family:Aptos,Bahnschrift,system-ui,sans-serif] lg:grid-cols-[260px_minmax(0,1fr)]";
const shellNoSidebar = "grid min-h-screen min-w-80 grid-cols-1 bg-[#111111] text-[#eeeeec] [color-scheme:dark] [font-family:Aptos,Bahnschrift,system-ui,sans-serif]";

export default function App() {
  const initialRoute = useMemo(() => routeFromPath(), []);
  const [mode, setMode] = useState(initialRoute.mode);
  const [selectedJobId, setSelectedJobId] = useState(initialRoute.jobId);
  const [currentWorldId, setCurrentWorldId] = useState(initialRoute.playWorldId);
  const [sidebarHidden, setSidebarHidden] = useState(initialRoute.mode === ROUTE_PLAY);
  const [error, setError] = useState("");

  const { worlds, loadWorlds } = useWorlds({ setError });
  const {
    models,
    activeModelId,
    modelStatus,
    modelTestResult,
    loadModels,
    selectModel,
    testModel,
  } = useModels({ setError });

  const navigateMode = useCallback((nextMode, { path = PATH_HOME, jobId = "", worldId = "" } = {}) => {
    if (window.location.pathname !== path) {
      window.history.pushState({}, "", path);
    }
    setMode(nextMode);
    setSelectedJobId(jobId);
    setCurrentWorldId(worldId);
    setSidebarHidden(nextMode === ROUTE_PLAY);
  }, []);

  const showCreate = useCallback(() => {
    setError("");
    navigateMode(ROUTE_CREATE);
  }, [navigateMode]);

  const showJobs = useCallback(() => {
    setError("");
    navigateMode(ROUTE_JOBS, { path: PATH_JOBS });
  }, [navigateMode]);

  const showJobDetail = useCallback((jobId) => {
    setError("");
    navigateMode(ROUTE_JOB_DETAIL, { path: jobDetailPath(jobId), jobId });
  }, [navigateMode]);

  const showWorld = useCallback((worldId) => {
    setError("");
    navigateMode(ROUTE_DETAIL, { worldId });
  }, [navigateMode]);

  const showPlay = useCallback((worldId) => {
    setError("");
    navigateMode(ROUTE_PLAY, { path: playPath(worldId), worldId });
  }, [navigateMode]);

  useEffect(() => {
    loadModels().catch((loadError) => setError(loadError.message));
    const startsOnJobsLike = isJobsLikePath(window.location.pathname);
    const startsOnPlayRoute = initialRoute.mode === ROUTE_PLAY && initialRoute.playWorldId;
    loadWorlds()
      .then((items) => {
        if (items.length > 0 && !startsOnJobsLike && !startsOnPlayRoute) {
          setCurrentWorldId(items[0].id);
          setMode(ROUTE_DETAIL);
        }
      })
      .catch(() => {});
  }, [loadModels, loadWorlds, initialRoute.mode, initialRoute.playWorldId]);

  useEffect(() => {
    const handlePopState = () => {
      const route = routeFromPath();
      setMode(route.mode);
      setSelectedJobId(route.jobId);
      if (route.mode === ROUTE_PLAY) {
        setCurrentWorldId(route.playWorldId);
      } else if (route.mode !== ROUTE_DETAIL) {
        setCurrentWorldId("");
      }
      setSidebarHidden(route.mode === ROUTE_PLAY);
    };
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  const handleAfterCreateWorld = useCallback(async () => {
    try {
      await loadWorlds();
    } catch {
      // already reported via setError in hook
    }
  }, [loadWorlds]);

  const handleAfterDeleteWorld = useCallback(async () => {
    const next = await loadWorlds();
    if (next.length > 0) {
      setCurrentWorldId(next[0].id);
      navigateMode(ROUTE_DETAIL, { worldId: next[0].id });
    } else {
      setCurrentWorldId("");
      navigateMode(ROUTE_CREATE);
    }
  }, [loadWorlds, navigateMode]);

  const refreshWorlds = useCallback(() => {
    loadWorlds().catch(() => {});
  }, [loadWorlds]);

  const onBackToWorld = useCallback((worldId) => showWorld(worldId), [showWorld]);
  const onPlayCurrentWorld = useCallback(() => showPlay(currentWorldId), [showPlay, currentWorldId]);
  const toggleSidebar = useCallback(() => setSidebarHidden((current) => !current), []);

  const createWorldNavigate = useCallback((nextMode, path) => navigateMode(nextMode, { path }), [navigateMode]);

  return (
    <div className={sidebarHidden ? shellNoSidebar : shellWithSidebar}>
      {!sidebarHidden ? (
        <Sidebar
          worlds={worlds}
          selectedWorldId={currentWorldId}
          onSelectWorld={showWorld}
          onNewWorld={showCreate}
          onShowJobs={showJobs}
          onRefresh={refreshWorlds}
          models={models}
          activeModelId={activeModelId}
          onSelectModel={selectModel}
          onTestModel={testModel}
          modelStatus={modelStatus}
          modelTestResult={modelTestResult}
        />
      ) : null}

      {mode === ROUTE_JOBS ? (
        <GenerationJobsPage
          active={mode === ROUTE_JOBS}
          setError={setError}
          error={error}
          activeModelId={activeModelId}
          onWorldsChanged={refreshWorlds}
          onSelectJob={showJobDetail}
          onOpenWorld={showWorld}
          onPlayWorld={showPlay}
        />
      ) : mode === ROUTE_JOB_DETAIL ? (
        <GenerationJobDetailPage
          jobId={selectedJobId}
          active={mode === ROUTE_JOB_DETAIL}
          setError={setError}
          error={error}
          activeModelId={activeModelId}
          onWorldsChanged={refreshWorlds}
          onBack={showJobs}
          onOpenWorld={showWorld}
          onPlayWorld={showPlay}
        />
      ) : mode === ROUTE_PLAY ? (
        <PlayPage
          worldId={currentWorldId}
          setError={setError}
          error={error}
          sidebarHidden={sidebarHidden}
          onToggleSidebar={toggleSidebar}
          onBackToWorld={onBackToWorld}
        />
      ) : mode === ROUTE_DETAIL && currentWorldId ? (
        <WorldDetailPage
          worldId={currentWorldId}
          setError={setError}
          onPlay={onPlayCurrentWorld}
          onAfterDelete={handleAfterDeleteWorld}
          onWorldsChanged={refreshWorlds}
        />
      ) : (
        <CreateWorldPage
          activeModelId={activeModelId}
          navigateMode={createWorldNavigate}
          setError={setError}
          error={error}
          onAfterCreate={handleAfterCreateWorld}
        />
      )}
    </div>
  );
}
