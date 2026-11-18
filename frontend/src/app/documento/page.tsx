import { Suspense } from "react";

import { TelaDocumento } from "./tela-documento";

/** Documento salvo: /documento?id=<uuid>. O id vem da URL, lido só no navegador. */
export default function PaginaDocumento() {
  return (
    <Suspense fallback={null}>
      <TelaDocumento />
    </Suspense>
  );
}
