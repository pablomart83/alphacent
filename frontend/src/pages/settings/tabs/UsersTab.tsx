import { useState } from 'react'
import { toast } from 'sonner'
import { KeyRound, Plus, Trash2 } from 'lucide-react'
import {
  Badge,
  Button,
  Card,
  ConfirmDialog,
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Input,
  Label,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/primitives'
import { SectionLabel } from '@/components/layout'
import { classifyError } from '@/lib/errors'
import { formatTimestamp } from '@/lib/utils'
import {
  useCreateUser,
  useDeleteUser,
  useResetUserPassword,
  useRoles,
  useUpdateUser,
  useUsers,
  type UserRecord,
} from '../useSettingsData'

/**
 * Users tab — admin CRUD over the authentication manager.
 * Silently degrades to a read-only "manage_users action required" banner
 * when the current user lacks permission.
 */
export function UsersTab() {
  const users = useUsers()
  const roles = useRoles()
  const create = useCreateUser()
  const update = useUpdateUser()
  const del = useDeleteUser()
  const reset = useResetUserPassword()
  const [dialogOpen, setDialogOpen] = useState(false)
  const [resetTarget, setResetTarget] = useState<string | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null)

  const roleOptions = Object.keys(roles.data?.roles ?? {}).sort()

  if (users.isError) {
    const info = classifyError(users.error, 'list users')
    if (info.status === 403) {
      return (
        <div className="max-w-[540px]">
          <Card padding="md" className="text-[11px] text-[var(--text-2)] leading-[16px]">
            Your account does not have the <code className="mono">manage_users</code> permission. Ask
            an admin to grant it or log in as admin to manage users here.
          </Card>
        </div>
      )
    }
    return (
      <Card padding="md" className="text-[11px] text-[var(--pnl-down)]">
        Couldn't load users: {info.message}
      </Card>
    )
  }

  const list = users.data?.users ?? []

  return (
    <div className="max-w-[960px] space-y-3">
      <div className="flex items-end justify-between">
        <div className="space-y-1">
          <SectionLabel className="mb-0">Users</SectionLabel>
          <p className="text-[12px] text-[var(--text-2)]">
            Admin-only. Create users, assign roles, reset passwords, toggle active status.
          </p>
        </div>
        <Button variant="primary" size="sm" onClick={() => setDialogOpen(true)}>
          <Plus className="h-3 w-3 mr-1" /> New user
        </Button>
      </div>

      <Card padding="sm">
        <table className="w-full text-[11px]">
          <thead>
            <tr className="text-left text-[9px] uppercase tracking-wider text-[var(--text-3)] border-b border-[var(--border-subtle)]">
              <th className="px-2 py-1.5">Username</th>
              <th className="px-2 py-1.5">Role</th>
              <th className="px-2 py-1.5">Active</th>
              <th className="px-2 py-1.5">Last login</th>
              <th className="px-2 py-1.5 text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {list.map((u) => (
              <UserRow
                key={u.username}
                user={u}
                roleOptions={roleOptions}
                onSetRole={async (role) => {
                  try {
                    await update.mutateAsync({ username: u.username, body: { role } })
                    toast.success(`${u.username} → ${role}`)
                  } catch (err) {
                    toast.error(classifyError(err, 'update role').message)
                  }
                }}
                onToggleActive={async (active) => {
                  try {
                    await update.mutateAsync({
                      username: u.username,
                      body: { is_active: active },
                    })
                    toast.success(`${u.username} ${active ? 'activated' : 'deactivated'}`)
                  } catch (err) {
                    toast.error(classifyError(err, 'toggle active').message)
                  }
                }}
                onReset={() => setResetTarget(u.username)}
                onDelete={() => setDeleteTarget(u.username)}
              />
            ))}
          </tbody>
        </table>
      </Card>

      <CreateUserDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        roleOptions={roleOptions}
        onSubmit={async (body) => {
          try {
            await create.mutateAsync(body)
            toast.success(`User ${body.username} created`)
            setDialogOpen(false)
          } catch (err) {
            toast.error(classifyError(err, 'create user').message)
          }
        }}
      />

      <ResetPasswordDialog
        open={resetTarget != null}
        username={resetTarget}
        onOpenChange={() => setResetTarget(null)}
        onSubmit={async (pw) => {
          if (!resetTarget) return
          try {
            await reset.mutateAsync({ username: resetTarget, new_password: pw })
            toast.success(`Password reset for ${resetTarget}`)
            setResetTarget(null)
          } catch (err) {
            toast.error(classifyError(err, 'reset password').message)
          }
        }}
      />

      <ConfirmDialog
        open={deleteTarget != null}
        onOpenChange={() => setDeleteTarget(null)}
        title={`Delete user ${deleteTarget}?`}
        description="This cannot be undone. The user will lose access immediately. You cannot delete yourself."
        confirmLabel="Delete user"
        confirmVariant="destructive"
        isLoading={del.isPending}
        onConfirm={async () => {
          if (!deleteTarget) return
          try {
            await del.mutateAsync(deleteTarget)
            toast.success(`${deleteTarget} deleted`)
            setDeleteTarget(null)
          } catch (err) {
            toast.error(classifyError(err, 'delete user').message)
          }
        }}
      />
    </div>
  )
}

function UserRow({
  user,
  roleOptions,
  onSetRole,
  onToggleActive,
  onReset,
  onDelete,
}: {
  user: UserRecord
  roleOptions: string[]
  onSetRole: (role: string) => void
  onToggleActive: (active: boolean) => void
  onReset: () => void
  onDelete: () => void
}) {
  return (
    <tr className="border-b border-[var(--border-subtle)] hover:bg-[var(--bg-hover)]">
      <td className="px-2 py-1.5 mono">{user.username}</td>
      <td className="px-2 py-1.5">
        <Select value={user.role} onValueChange={onSetRole}>
          <SelectTrigger size="sm" className="w-[120px]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {roleOptions.map((r) => (
              <SelectItem key={r} value={r}>
                {r}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </td>
      <td className="px-2 py-1.5">
        <Badge variant={user.is_active ? 'success' : 'default'} size="sm">
          {user.is_active ? 'active' : 'inactive'}
        </Badge>
      </td>
      <td className="px-2 py-1.5 mono tabular-nums text-[10px] text-[var(--text-2)]">
        {user.last_login ? formatTimestamp(user.last_login, 'short') : '—'}
      </td>
      <td className="px-2 py-1.5 text-right space-x-1">
        <Button
          size="sm"
          variant="ghost"
          onClick={() => onToggleActive(!user.is_active)}
        >
          {user.is_active ? 'Deactivate' : 'Activate'}
        </Button>
        <Button size="sm" variant="ghost" onClick={onReset}>
          <KeyRound className="h-3 w-3" />
        </Button>
        <Button size="sm" variant="ghost" onClick={onDelete}>
          <Trash2 className="h-3 w-3 text-[var(--pnl-down)]" />
        </Button>
      </td>
    </tr>
  )
}

function CreateUserDialog({
  open,
  onOpenChange,
  roleOptions,
  onSubmit,
}: {
  open: boolean
  onOpenChange: (v: boolean) => void
  roleOptions: string[]
  onSubmit: (b: { username: string; password: string; role: string }) => void
}) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [role, setRole] = useState(roleOptions[0] ?? 'viewer')
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="md">
        <DialogHeader>
          <DialogTitle>Create user</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1">
            <Label className="text-[10px] uppercase tracking-wider text-[var(--text-3)]">
              Username
            </Label>
            <Input
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="mono"
              autoComplete="off"
            />
          </div>
          <div className="space-y-1">
            <Label className="text-[10px] uppercase tracking-wider text-[var(--text-3)]">
              Password
            </Label>
            <Input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="mono"
              autoComplete="new-password"
            />
          </div>
          <div className="space-y-1">
            <Label className="text-[10px] uppercase tracking-wider text-[var(--text-3)]">
              Role
            </Label>
            <Select value={role} onValueChange={setRole}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {roleOptions.map((r) => (
                  <SelectItem key={r} value={r}>
                    {r}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
        <DialogFooter>
          <Button variant="ghost" size="sm" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            variant="primary"
            size="sm"
            onClick={() => onSubmit({ username, password, role })}
            disabled={!username || !password}
          >
            Create
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function ResetPasswordDialog({
  open,
  username,
  onOpenChange,
  onSubmit,
}: {
  open: boolean
  username: string | null
  onOpenChange: (v: boolean) => void
  onSubmit: (pw: string) => void
}) {
  const [pw, setPw] = useState('')
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="sm">
        <DialogHeader>
          <DialogTitle>Reset password for {username}</DialogTitle>
        </DialogHeader>
        <div className="space-y-1">
          <Label className="text-[10px] uppercase tracking-wider text-[var(--text-3)]">
            New password
          </Label>
          <Input
            type="password"
            value={pw}
            onChange={(e) => setPw(e.target.value)}
            className="mono"
            autoComplete="new-password"
          />
        </div>
        <DialogFooter>
          <Button variant="ghost" size="sm" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button variant="primary" size="sm" onClick={() => onSubmit(pw)} disabled={!pw}>
            Reset password
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
