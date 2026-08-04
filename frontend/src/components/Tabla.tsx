"use client";

import {
  ColumnDef,
  flexRender,
  getCoreRowModel,
  getFilteredRowModel,
  getSortedRowModel,
  SortingState,
  useReactTable,
} from "@tanstack/react-table";
import { useState } from "react";

export function Tabla<T>({
  columnas,
  datos,
  buscador = true,
  vacio = "sin filas",
}: {
  columnas: ColumnDef<T, unknown>[];
  datos: T[];
  buscador?: boolean;
  vacio?: string;
}) {
  const [orden, setOrden] = useState<SortingState>([]);
  const [filtro, setFiltro] = useState("");

  const tabla = useReactTable({
    data: datos,
    columns: columnas,
    state: { sorting: orden, globalFilter: filtro },
    onSortingChange: setOrden,
    onGlobalFilterChange: setFiltro,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
  });

  return (
    <div>
      {buscador ? (
        <input
          className="campo mb-2 w-64"
          placeholder="filtrar..."
          value={filtro}
          onChange={(e) => setFiltro(e.target.value)}
        />
      ) : null}
      <div className="overflow-x-auto">
        <table className="tabla">
          <thead>
            {tabla.getHeaderGroups().map((grupo) => (
              <tr key={grupo.id}>
                {grupo.headers.map((encabezado) => (
                  <th
                    key={encabezado.id}
                    onClick={encabezado.column.getToggleSortingHandler()}
                    className="cursor-pointer select-none whitespace-nowrap"
                  >
                    {flexRender(encabezado.column.columnDef.header, encabezado.getContext())}
                    {{ asc: " ↑", desc: " ↓" }[encabezado.column.getIsSorted() as string] ?? ""}
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {tabla.getRowModel().rows.length === 0 ? (
              <tr>
                <td colSpan={columnas.length} className="py-4 text-center text-slate-500">
                  {vacio}
                </td>
              </tr>
            ) : (
              tabla.getRowModel().rows.map((fila) => (
                <tr key={fila.id} className="hover:bg-slate-50">
                  {fila.getVisibleCells().map((celda) => (
                    <td key={celda.id}>
                      {flexRender(celda.column.columnDef.cell, celda.getContext())}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
