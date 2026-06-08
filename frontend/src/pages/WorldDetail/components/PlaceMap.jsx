import React from "react";
import { MapPin } from "lucide-react";
import { cx } from "../../../shared/lib/classNames.js";

export default function PlaceMap({ places, selectedId, onSelect }) {
  return (
    <div className="relative m-4 h-[420px] overflow-hidden rounded-lg border border-[#35332f] bg-[#181818] [background-image:linear-gradient(#25231f_1px,transparent_1px),linear-gradient(90deg,#25231f_1px,transparent_1px)] [background-size:40px_40px]">
      {places.map((place) => (
        <button
          key={place.id}
          className={cx(
            "absolute flex h-7 w-7 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-[7px] border border-[#3a3834] bg-[#24231f] text-[#d7c4a7]",
            Number(place.danger_level) >= 4 && "text-[#e2a09a]",
            selectedId === place.id && "border-[#d29a55] bg-[#3a2a18]",
          )}
          style={{ left: `${place.x}%`, top: `${place.y}%` }}
          onClick={() => onSelect(place)}
          title={`${place.name} (${place.place_type})`}
        >
          <MapPin size={15} />
        </button>
      ))}
    </div>
  );
}
