import Image from "next/image";

/** Logo horizontal; a versão escura troca o azul-marinho por branco para manter o contraste. */
export function Logo({ className = "h-9 w-auto" }: { className?: string }) {
  return (
    <>
      <Image
        src="/marca/miniscan-logo.png"
        alt="MiniScan"
        width={960}
        height={261}
        priority
        className={`${className} dark:hidden`}
      />
      <Image
        src="/marca/miniscan-logo-escuro.png"
        alt="MiniScan"
        width={960}
        height={261}
        priority
        className={`${className} hidden dark:block`}
      />
    </>
  );
}
