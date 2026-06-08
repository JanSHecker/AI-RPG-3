export const ROUTE_CREATE = "create";
export const ROUTE_JOBS = "jobs";
export const ROUTE_JOB_DETAIL = "job-detail";
export const ROUTE_DETAIL = "detail";
export const ROUTE_PLAY = "play";

export const PATH_HOME = "/";
export const PATH_JOBS = "/jobs";

export const jobDetailPath = (jobId) => `/jobs/${encodeURIComponent(jobId)}`;
export const playPath = (worldId) => `/play/${encodeURIComponent(worldId)}`;

export function routeFromPath() {
  const playMatch = window.location.pathname.match(/^\/play\/([^/]+)$/);
  if (playMatch) {
    return { mode: ROUTE_PLAY, jobId: "", playWorldId: decodeURIComponent(playMatch[1]) };
  }
  const jobDetailMatch = window.location.pathname.match(/^\/jobs\/([^/]+)$/);
  if (jobDetailMatch) {
    return { mode: ROUTE_JOB_DETAIL, jobId: decodeURIComponent(jobDetailMatch[1]), playWorldId: "" };
  }
  if (window.location.pathname === PATH_JOBS) {
    return { mode: ROUTE_JOBS, jobId: "", playWorldId: "" };
  }
  return { mode: ROUTE_CREATE, jobId: "", playWorldId: "" };
}

export function isJobsLikePath(pathname) {
  return pathname === PATH_JOBS || pathname.startsWith("/jobs/");
}
