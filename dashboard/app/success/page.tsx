import Link from "next/link";
import Image from "next/image";

export default function SuccessPage() {
  return (
    <div
      className="min-h-screen flex flex-col items-center justify-center px-6 text-center"
      style={{ background: "var(--background)", color: "var(--foreground)" }}
    >
      <Image src="/logo.png" alt="BudgetForge" width={48} height={48} className="rounded-xl mb-6" />

      <div
        className="w-12 h-12 rounded-full flex items-center justify-center text-2xl mb-6"
        style={{ background: "#4ade8022", border: "1px solid #4ade80" }}
      >
        ✓
      </div>

      <h1 className="text-2xl font-bold mb-3">Payment confirmed!</h1>
      <p className="text-sm mb-2 max-w-sm" style={{ color: "var(--muted)" }}>
        Check your email — your BudgetForge API key and setup instructions are on their way.
      </p>
      <p className="text-xs mb-8" style={{ color: "var(--muted)" }}>
        Didn&apos;t receive anything? Check your spam folder or contact{" "}
        <a href="mailto:support@maxiaworld.app" style={{ color: "var(--amber)" }}>
          support@maxiaworld.app
        </a>
      </p>

      <Link
        href="/"
        className="px-6 py-2.5 rounded-lg font-semibold text-sm transition-opacity hover:opacity-90"
        style={{ background: "var(--amber)", color: "#000" }}
      >
        Back to home
      </Link>
    </div>
  );
}
