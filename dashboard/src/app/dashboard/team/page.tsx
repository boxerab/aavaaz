"use client";

import { useCallback, useEffect, useState } from "react";
import { UserPlus, Shield, Trash2, Mail, Crown } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { team, TeamMember, TeamRole } from "@/lib/api";

type DisplayRole = "owner" | TeamRole;

const ROLE_COLORS: Record<DisplayRole, string> = {
  owner: "bg-amber-500/10 text-amber-400",
  admin: "bg-purple-500/10 text-purple-400",
  member: "bg-blue-500/10 text-blue-400",
  viewer: "bg-muted text-muted-foreground",
};

const ROLE_PERMISSIONS: Record<DisplayRole, string> = {
  owner: "Full access, billing, delete workspace",
  admin: "Manage team, API keys, settings",
  member: "Use API, view transcripts, upload files",
  viewer: "View transcripts and logs only",
};

function nameFromEmail(email: string): string {
  return email.split("@")[0] || email;
}

export default function TeamPage() {
  const { user, getToken } = useAuth();
  const [members, setMembers] = useState<TeamMember[]>([]);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState<TeamRole>("member");
  const [showInvite, setShowInvite] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const token = await getToken();
    if (!token) return;
    try {
      setMembers(await team.list(token));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load team");
    }
  }, [getToken]);

  useEffect(() => {
    load();
  }, [load]);

  async function inviteMember() {
    const email = inviteEmail.trim();
    if (!email) return;
    setBusy(true);
    setError("");
    try {
      const token = await getToken();
      if (!token) return;
      const member = await team.invite(token, email, inviteRole);
      setMembers((prev) => [...prev, member]);
      setInviteEmail("");
      setShowInvite(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to invite member");
    } finally {
      setBusy(false);
    }
  }

  async function removeMember(id: string) {
    const token = await getToken();
    if (!token) return;
    try {
      await team.remove(token, id);
      setMembers((prev) => prev.filter((m) => m.id !== id));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to remove member");
    }
  }

  async function changeRole(id: string, role: TeamRole) {
    const token = await getToken();
    if (!token) return;
    const prev = members;
    setMembers((ms) => ms.map((m) => (m.id === id ? { ...m, role } : m)));
    try {
      await team.updateRole(token, id, role);
    } catch (e) {
      setMembers(prev); // revert on failure
      setError(e instanceof Error ? e.message : "Failed to update role");
    }
  }

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Team Management</h1>
          <p className="text-muted-foreground mt-1">
            Invite team members and manage access roles
          </p>
        </div>
        <button
          onClick={() => setShowInvite(!showInvite)}
          className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
        >
          <UserPlus className="h-4 w-4" />
          Invite Member
        </button>
      </div>

      {error && (
        <div className="rounded-lg border border-red-500/30 bg-red-500/5 px-4 py-3 text-sm text-red-300">
          {error}
        </div>
      )}

      {/* Invite form */}
      {showInvite && (
        <div className="rounded-lg border bg-card p-5 space-y-4">
          <h3 className="font-semibold">Invite a team member</h3>
          <div className="flex gap-3">
            <div className="flex-1">
              <input
                type="email"
                value={inviteEmail}
                onChange={(e) => setInviteEmail(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && inviteMember()}
                placeholder="colleague@company.com"
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
              />
            </div>
            <select
              value={inviteRole}
              onChange={(e) => setInviteRole(e.target.value as TeamRole)}
              className="rounded-md border border-input bg-background px-3 py-2 text-sm"
            >
              <option value="admin">Admin</option>
              <option value="member">Member</option>
              <option value="viewer">Viewer</option>
            </select>
            <button
              onClick={inviteMember}
              disabled={!inviteEmail.trim() || busy}
              className="inline-flex items-center gap-1.5 px-4 py-2 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 disabled:opacity-50 transition-colors"
            >
              <Mail className="h-3.5 w-3.5" />
              Send Invite
            </button>
          </div>
        </div>
      )}

      {/* Members table */}
      <div className="rounded-lg border bg-card overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b bg-muted/50">
              <th className="text-left px-4 py-3 font-medium text-muted-foreground">Member</th>
              <th className="text-left px-4 py-3 font-medium text-muted-foreground">Role</th>
              <th className="text-left px-4 py-3 font-medium text-muted-foreground">Joined</th>
              <th className="text-right px-4 py-3 font-medium text-muted-foreground">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {/* current user is always the owner */}
            {user && (
              <tr className="hover:bg-muted/30 transition-colors">
                <td className="px-4 py-3">
                  <div className="flex items-center gap-3">
                    <div className="h-8 w-8 rounded-full bg-primary/10 flex items-center justify-center text-xs font-medium text-primary">
                      {nameFromEmail(user.email).charAt(0).toUpperCase()}
                    </div>
                    <div>
                      <p className="font-medium text-foreground">{nameFromEmail(user.email)}</p>
                      <p className="text-xs text-muted-foreground">{user.email}</p>
                    </div>
                  </div>
                </td>
                <td className="px-4 py-3">
                  <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium ${ROLE_COLORS.owner}`}>
                    <Crown className="h-3 w-3" />
                    Owner
                  </span>
                </td>
                <td className="px-4 py-3 text-muted-foreground text-xs">&mdash;</td>
                <td className="px-4 py-3" />
              </tr>
            )}
            {members.map((member) => (
              <tr key={member.id} className="hover:bg-muted/30 transition-colors">
                <td className="px-4 py-3">
                  <div className="flex items-center gap-3">
                    <div className="h-8 w-8 rounded-full bg-primary/10 flex items-center justify-center text-xs font-medium text-primary">
                      {nameFromEmail(member.email).charAt(0).toUpperCase()}
                    </div>
                    <div>
                      <p className="font-medium text-foreground">{nameFromEmail(member.email)}</p>
                      <p className="text-xs text-muted-foreground">{member.email}</p>
                    </div>
                  </div>
                </td>
                <td className="px-4 py-3">
                  <select
                    value={member.role}
                    onChange={(e) => changeRole(member.id, e.target.value as TeamRole)}
                    className={`text-xs font-medium px-2 py-0.5 rounded border-0 bg-transparent cursor-pointer ${ROLE_COLORS[member.role]}`}
                  >
                    <option value="admin">Admin</option>
                    <option value="member">Member</option>
                    <option value="viewer">Viewer</option>
                  </select>
                </td>
                <td className="px-4 py-3 text-muted-foreground text-xs">
                  {member.created_at ? member.created_at.slice(0, 10) : "—"}
                </td>
                <td className="px-4 py-3 text-right">
                  <button
                    onClick={() => removeMember(member.id)}
                    className="p-1.5 rounded text-muted-foreground hover:text-red-400 transition-colors"
                    title="Remove member"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Roles explanation */}
      <div className="rounded-lg border bg-card p-5">
        <div className="flex items-center gap-2 mb-3">
          <Shield className="h-4 w-4 text-primary" />
          <h3 className="font-semibold">Role Permissions</h3>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {(Object.entries(ROLE_PERMISSIONS) as [DisplayRole, string][]).map(([role, desc]) => (
            <div key={role} className="flex items-start gap-2">
              <span className={`inline-flex px-2 py-0.5 rounded text-xs font-medium mt-0.5 ${ROLE_COLORS[role]}`}>
                {role}
              </span>
              <span className="text-sm text-muted-foreground">{desc}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
