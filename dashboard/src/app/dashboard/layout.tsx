"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/lib/auth";
import {
  LayoutDashboard,
  Key,
  BarChart3,
  CreditCard,
  FileAudio,
  Mic,
  Settings,
  Upload,
  Code2,
  ScrollText,
  BookOpen,
  Users,
  Plug2,
  Activity,
  LogOut,
} from "lucide-react";

const navItems = [
  { href: "/dashboard", label: "Overview", icon: LayoutDashboard },
  { href: "/dashboard/upload", label: "File Upload", icon: Upload },
  { href: "/dashboard/live", label: "Live Demo", icon: Mic },
  { href: "/dashboard/playground", label: "API Playground", icon: Code2 },
  { href: "/dashboard/keys", label: "API Keys", icon: Key },
  { href: "/dashboard/vocabulary", label: "Vocabulary", icon: BookOpen },
  { href: "/dashboard/settings", label: "Features", icon: Settings },
  { href: "/dashboard/integrations", label: "Integrations", icon: Plug2 },
  { href: "/dashboard/team", label: "Team", icon: Users },
  { href: "/dashboard/logs", label: "Request Logs", icon: ScrollText },
  { href: "/dashboard/usage", label: "Usage", icon: BarChart3 },
  { href: "/dashboard/billing", label: "Billing", icon: CreditCard },
  { href: "/dashboard/transcripts", label: "Transcripts", icon: FileAudio },
  { href: "/dashboard/status", label: "Status", icon: Activity },
];

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { user, loading, logout } = useAuth();
  const router = useRouter();

  useEffect(() => {
    // Auth guard disabled for local preview (re-enable for production)
    // if (!loading && !user) {
    //   router.push("/login");
    // }
  }, [user, loading, router]);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-pulse text-muted-foreground">Loading...</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex">
      {/* Sidebar */}
      <aside className="w-64 border-r bg-card flex flex-col">
        <div className="p-6 border-b">
          <Link href="/dashboard" className="text-xl font-bold text-foreground">
            Aavaaz
          </Link>
          <p className="text-xs text-muted-foreground mt-1">
            Speech-to-Text Platform
          </p>
        </div>

        <nav className="flex-1 p-4 space-y-1">
          {navItems.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className="flex items-center gap-3 px-3 py-2 rounded-md text-sm text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
            >
              <item.icon className="h-4 w-4" />
              {item.label}
            </Link>
          ))}
        </nav>

        <div className="p-4 border-t">
          <div className="text-sm text-muted-foreground truncate mb-2">
            {user?.email || "Preview Mode"}
          </div>
          <button
            onClick={() => logout().then(() => router.push("/"))}
            className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors"
          >
            <LogOut className="h-4 w-4" />
            Sign out
          </button>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-auto">
        <div className="p-8 max-w-6xl mx-auto">{children}</div>
      </main>
    </div>
  );
}
