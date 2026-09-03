import Link from "next/link";
import { Button } from "@/components/ui/button";

export default function NotFound() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-3 bg-background px-6 text-center">
      <p className="font-display text-2xl font-medium text-foreground">Page not found</p>
      <p className="max-w-sm text-sm text-muted-foreground">
        The page you&apos;re looking for doesn&apos;t exist or may have moved.
      </p>
      <Button asChild className="mt-2">
        <Link href="/">Back to dashboard</Link>
      </Button>
    </div>
  );
}
