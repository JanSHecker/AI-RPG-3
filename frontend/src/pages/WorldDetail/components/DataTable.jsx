import React, { useMemo, useState } from "react";
import { flexRender, getCoreRowModel, getSortedRowModel, useReactTable } from "@tanstack/react-table";
import { cx } from "../../../shared/lib/classNames.js";
import { emptyPanel, td, th } from "../../../shared/ui/classes.js";

export default function DataTable({ rows, columns, onRowClick, selectedId }) {
  const [sorting, setSorting] = useState([]);
  const tableColumns = useMemo(
    () => columns.map((column) => ({
      id: column.key,
      accessorKey: column.key,
      header: column.label,
      cell: ({ row, getValue }) => (column.render ? column.render(row.original) : getValue()),
    })),
    [columns],
  );
  const table = useReactTable({
    data: rows,
    columns: tableColumns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });

  if (!rows.length) {
    return <div className={emptyPanel}>No records.</div>;
  }

  return (
    <div className="overflow-auto">
      <table className="w-full min-w-[760px] border-collapse">
        <thead>
          {table.getHeaderGroups().map((headerGroup) => (
            <tr key={headerGroup.id}>
              {headerGroup.headers.map((header) => (
                <th key={header.id} className={th}>
                  {header.isPlaceholder ? null : (
                    <button
                      className="inline-flex min-h-0 w-full items-center gap-2 border-0 bg-transparent p-0 text-left font-[inherit] text-inherit"
                      type="button"
                      onClick={header.column.getToggleSortingHandler()}
                    >
                      {flexRender(header.column.columnDef.header, header.getContext())}
                      <span className="text-[11px] font-medium text-[#aaa49a]">
                        {header.column.getIsSorted() === "asc" ? "Asc" : header.column.getIsSorted() === "desc" ? "Desc" : ""}
                      </span>
                    </button>
                  )}
                </th>
              ))}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.map((row) => (
            <tr
              key={row.original.id ?? row.id}
              className={cx(
                "transition-colors duration-150 hover:bg-[#20201e]",
                selectedId === row.original.id && "bg-[#20201e]",
                onRowClick && "cursor-pointer",
              )}
              onClick={() => onRowClick?.(row.original)}
            >
              {row.getVisibleCells().map((cell) => (
                <td key={cell.id} className={td}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
