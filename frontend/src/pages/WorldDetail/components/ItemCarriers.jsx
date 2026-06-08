import React from "react";
import { emptyPanel, label } from "../../../shared/ui/classes.js";
import DataTable from "./DataTable.jsx";

export default function ItemCarriers({ item }) {
  const carriers = item?.carriers ?? [];
  return (
    <section className="border-t border-[#2e2e2c]">
      <div className="border-b border-[#2e2e2c] p-4">
        <div>
          <div className={label}>Carried by</div>
          <p className="mt-2 leading-[1.55]">{item ? `${item.name} is currently carried by ${item.carrier_count} NPC${item.carrier_count === 1 ? "" : "s"}.` : "Select an item to inspect who carries it."}</p>
        </div>
      </div>
      {carriers.length === 0 ? (
        <div className={emptyPanel}>No one is carrying this item right now.</div>
      ) : (
        <DataTable
          rows={carriers}
          columns={[
            { key: "npc_name", label: "NPC" },
            { key: "quantity", label: "Qty" },
            { key: "condition", label: "Condition" },
            { key: "note", label: "Note" },
          ]}
        />
      )}
    </section>
  );
}
