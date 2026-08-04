import type { Metadata } from "next";
import Link from "next/link";

import "./globals.css";

export const metadata: Metadata = {
  title: "Tablero AnyLogic",
  description: "Resultados de la red logistica simulada en AnyLogic (ADR-064)",
};

const NAVEGACION = [
  { href: "/", texto: "Corridas" },
  { href: "/importar", texto: "Importar" },
  { href: "/comparar", texto: "Comparar" },
];

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es">
      <body>
        <header className="border-b border-borde bg-white">
          <div className="mx-auto flex max-w-7xl items-center gap-6 px-6 py-3">
            <Link href="/" className="text-base font-semibold text-acento">
              Tablero AnyLogic
            </Link>
            <nav className="flex gap-4 text-sm">
              {NAVEGACION.map((item) => (
                <Link key={item.href} href={item.href} className="hover:text-acento">
                  {item.texto}
                </Link>
              ))}
            </nav>
          </div>
        </header>
        <main className="mx-auto max-w-7xl px-6 py-6">{children}</main>
      </body>
    </html>
  );
}
