import { cx } from "./classNames.js";

const statusDotBase = "inline-block h-2 w-2 rounded-full bg-[#5f5a54]";

export function statusDotClass(status) {
  const statusColor = {
    running: "bg-[#b98241]",
    retrying: "bg-[#b98241]",
    done: "bg-[#6f9f74]",
    failed: "bg-[#c06b62]",
  }[status];
  return cx(statusDotBase, statusColor);
}
