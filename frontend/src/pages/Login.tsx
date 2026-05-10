import { useState, type FormEvent } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { Lock, User as UserIcon } from 'lucide-react'
import { Button, Input, Label } from '@/components/primitives'
import { useLogin } from '@/hooks/useAuth'
import { classifyError } from '@/lib/errors'
import { toast } from 'sonner'

interface LoginLocationState {
  from?: { pathname: string }
}

export function Login() {
  const navigate = useNavigate()
  const location = useLocation()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const loginMutation = useLogin()

  const handleSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    try {
      await loginMutation.mutateAsync({ username, password })
      const state = location.state as LoginLocationState | null
      navigate(state?.from?.pathname ?? '/', { replace: true })
    } catch (err) {
      const classified = classifyError(err, 'login')
      toast.error(classified.title, { description: classified.message })
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-[var(--bg-0)] p-4">
      <div className="w-full max-w-[360px] rounded-[4px] border border-[var(--border-default)] bg-[var(--bg-1)] p-6 shadow-xl">
        <div className="flex items-center gap-2 mb-5">
          <svg width={22} height={22} viewBox="0 0 32 32" aria-hidden>
            <rect width="32" height="32" rx="4" fill="var(--bg-2)" />
            <path
              d="M7 23 L13 9 L19 23 M9.5 18 L16.5 18"
              stroke="var(--pnl-up)"
              strokeWidth={2.2}
              fill="none"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
            <circle cx={24} cy={23} r={2} fill="var(--pnl-up)" />
          </svg>
          <div>
            <h1 className="text-[15px] font-semibold text-[var(--text-0)] leading-none">AlphaCent</h1>
            <p className="text-[10px] text-[var(--text-2)] mt-0.5">Autonomous trading platform</p>
          </div>
        </div>

        <form className="flex flex-col gap-3" onSubmit={handleSubmit} noValidate>
          <div className="flex flex-col gap-1">
            <Label htmlFor="username">Username</Label>
            <Input
              id="username"
              name="username"
              autoComplete="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              prefix={<UserIcon className="h-3.5 w-3.5" />}
              required
              disabled={loginMutation.isPending}
            />
          </div>
          <div className="flex flex-col gap-1">
            <Label htmlFor="password">Password</Label>
            <Input
              id="password"
              name="password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              prefix={<Lock className="h-3.5 w-3.5" />}
              required
              disabled={loginMutation.isPending}
            />
          </div>
          <Button
            type="submit"
            variant="primary"
            className="mt-2"
            loading={loginMutation.isPending}
          >
            Sign in
          </Button>
        </form>

        <p className="mt-4 text-[10px] text-[var(--text-3)] text-center">
          v2.0.0 · {import.meta.env.VITE_BUILD_SHA?.slice(0, 7) ?? 'dev'}
        </p>
      </div>
    </div>
  )
}
