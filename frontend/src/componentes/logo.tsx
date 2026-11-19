import Image from "next/image";

/** Logo horizontal do MiniScan. */
export function Logo({ className = "h-9 w-auto" }: { className?: string }) {
  return (
    <Image src="/marca/miniscan-logo.png" alt="MiniScan" width={960} height={261} priority className={className} />
  );
}
