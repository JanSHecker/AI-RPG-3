import React from "react";
import { Eye, Heart, MessageSquare, Shield, Sparkles } from "lucide-react";
import { cx } from "../../../shared/lib/classNames.js";

const sideSection = "grid gap-2.5 rounded-lg border border-[#2e2e2c] bg-[#171716] p-3.5";
const sideHeading = "m-0 flex items-center gap-[9px] text-[15px] font-semibold text-[#d7c4a7]";
const questPanel = "grid h-[360px] min-h-[360px] max-h-[360px] grid-rows-[auto_1fr] overflow-hidden";
const characterStat = "grid grid-cols-[18px_1fr_auto] items-center gap-2 text-[13px] text-[#cfc7ba]";
const statTrack = "h-[3px] bg-[rgba(143,150,160,0.18)]";
const statFill = "block h-full";
const characterAttribute = "flex justify-between gap-3";

export default function PlaySidePanels({ character }) {
  return (
    <aside className="grid gap-4">
      <section className={cx(sideSection, questPanel)}>
        <h2 className={sideHeading}><MessageSquare size={17} /> Quest Log</h2>
        <div className="min-h-0 border-t border-[rgba(143,150,160,0.12)]" aria-label="No quests tracked yet" />
      </section>

      <section className={sideSection}>
        <h2 className={sideHeading}><Shield size={17} /> Character</h2>
        <div className="grid grid-cols-[86px_minmax(0,1fr)] items-center gap-[18px]">
          <div className="grid h-[86px] w-[86px] place-items-center rounded-full border border-[rgba(143,150,160,0.25)] bg-[radial-gradient(circle_at_50%_35%,#2a2524,#090b0d_70%)] text-[34px] text-[#d8d1c5]">
            {(character?.name ?? "K").slice(0, 1)}
          </div>
          <div>
            <h3 className="m-0 text-[22px] font-medium text-[#f0eadf]">{character?.name ?? "Kaelen Duskborn"}</h3>
            <div className="mt-1 text-sm text-[#b78aff]">Level 12 - Shadowforged Rogue</div>
          </div>
        </div>
        <div className="mt-3.5 grid gap-1.5">
          <div className={cx(characterStat, "text-[#ef6969]")}><Heart size={15} /><span>Health</span><strong>736 / 736</strong></div>
          <div className={statTrack}><span className={cx(statFill, "w-full bg-[#ef6969]")} /></div>
          <div className={cx(characterStat, "text-[#6aa7dc]")}><Sparkles size={15} /><span>Mana</span><strong>312 / 412</strong></div>
          <div className={statTrack}><span className={cx(statFill, "w-[76%] bg-[#6aa7dc]")} /></div>
          <div className={cx(characterStat, "text-[#b78aff]")}><Eye size={15} /><span>Focus</span><strong>90 / 110</strong></div>
          <div className={statTrack}><span className={cx(statFill, "w-[82%] bg-[#b78aff]")} /></div>
        </div>
        <div className="mt-[18px] grid grid-cols-2 gap-x-[26px] gap-y-2.5 border-t border-[rgba(143,150,160,0.12)] pt-3.5 text-sm text-[#cfc7ba]">
          <span className={characterAttribute}>Strength <strong>14</strong></span>
          <span className={characterAttribute}>Intelligence <strong>13</strong></span>
          <span className={characterAttribute}>Dexterity <strong>19</strong></span>
          <span className={characterAttribute}>Wisdom <strong>12</strong></span>
          <span className={characterAttribute}>Constitution <strong>15</strong></span>
          <span className={characterAttribute}>Charisma <strong>10</strong></span>
        </div>
      </section>
    </aside>
  );
}
