"use client"

import { useState } from "react"
import { useRouter, useSearchParams } from "next/navigation"
import Link from "next/link"
import { Shield, Eye, EyeOff, Loader2 } from "lucide-react"

import { useLogin } from "@/lib/api/auth"
import { StrixApiError } from "@/lib/api/client"

export default function LoginPage() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const login = useLogin()
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState("")

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError("")
    try {
      await login.mutateAsync({ email, password })
      const next = searchParams.get("next")
      const safeNext = next && next.startsWith("/") && !next.startsWith("//") ? next : "/"
      router.push(safeNext)
    } catch (exc) {
      if (exc instanceof StrixApiError && exc.status === 401) {
        setError("Invalid email or password")
      } else if (exc instanceof StrixApiError) {
        setError(exc.problem?.detail ?? exc.message)
      } else {
        setError("Authentication failed — backend unreachable")
      }
    }
  }

  const loading = login.isPending

  return (
    <div className="space-y-8">
      {/* Mobile logo */}
      <div className="lg:hidden flex items-center gap-3 mb-8">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-strix-primary/20 to-strix-primary/5 border border-strix-primary/30">
          <Shield className="h-5 w-5 text-strix-primary" />
        </div>
        <div>
          <h1 className="text-xl font-bold tracking-widest text-[var(--strix-text)]">
            STRIX
          </h1>
          <p className="text-[9px] text-[var(--strix-text-muted)] tracking-[0.3em] uppercase">
            Vigilant Sentinel
          </p>
        </div>
      </div>

      {/* Header */}
      <div className="space-y-2">
        <h2 className="text-2xl font-bold text-[var(--strix-text)]">
          Sentinel Authentication
        </h2>
        <p className="text-sm text-[var(--strix-text-muted)]">
          Enter your credentials to access the STRIX network
        </p>
      </div>

      {/* Form */}
      <form onSubmit={handleSubmit} className="space-y-5">
        {/* Email */}
        <div className="space-y-2">
          <label className="text-xs font-medium text-[var(--strix-text)] uppercase tracking-wider">
            Operator Designation
          </label>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="sentinel@strix.intel"
            required
            className="w-full rounded-lg border border-[var(--strix-border)] bg-[var(--strix-bg-surface)] px-4 py-3 text-sm text-[var(--strix-text)] placeholder:text-[var(--strix-text-muted)] outline-none transition-colors focus:border-strix-primary dark:focus:border-strix-cyan focus:ring-1 focus:ring-strix-primary/20 dark:focus:ring-strix-cyan/20"
          />
        </div>

        {/* Password */}
        <div className="space-y-2">
          <label className="text-xs font-medium text-[var(--strix-text)] uppercase tracking-wider">
            Access Key
          </label>
          <div className="relative">
            <input
              type={showPassword ? "text" : "password"}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••••••"
              required
              className="w-full rounded-lg border border-[var(--strix-border)] bg-[var(--strix-bg-surface)] px-4 py-3 pr-10 text-sm text-[var(--strix-text)] placeholder:text-[var(--strix-text-muted)] outline-none transition-colors focus:border-strix-primary dark:focus:border-strix-cyan focus:ring-1 focus:ring-strix-primary/20 dark:focus:ring-strix-cyan/20"
            />
            <button
              type="button"
              onClick={() => setShowPassword(!showPassword)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-[var(--strix-text-muted)] hover:text-[var(--strix-text)]"
            >
              {showPassword ? (
                <EyeOff className="h-4 w-4" />
              ) : (
                <Eye className="h-4 w-4" />
              )}
            </button>
          </div>
        </div>

        {/* Remember + Forgot */}
        <div className="flex items-center justify-between">
          <label className="flex items-center gap-2 text-xs text-[var(--strix-text-muted)] cursor-pointer">
            <input
              type="checkbox"
              className="rounded border-[var(--strix-border)] text-strix-primary focus:ring-strix-primary/20"
            />
            Remember terminal
          </label>
          <button
            type="button"
            className="text-xs text-strix-primary dark:text-strix-cyan hover:underline"
          >
            Reset access key
          </button>
        </div>

        {/* Error */}
        {error && (
          <div className="rounded-lg bg-red-500/10 border border-red-500/20 px-4 py-3 text-xs text-red-500">
            {error}
          </div>
        )}

        {/* Submit */}
        <button
          type="submit"
          disabled={loading}
          className="w-full rounded-lg bg-strix-primary dark:bg-strix-cyan py-3 text-sm font-semibold text-white dark:text-strix-bg-dark tracking-wider uppercase transition-all hover:opacity-90 disabled:opacity-50 flex items-center justify-center gap-2"
        >
          {loading ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              Authenticating...
            </>
          ) : (
            "Initialize Session"
          )}
        </button>
      </form>

      {/* Register link */}
      <p className="text-center text-xs text-[var(--strix-text-muted)]">
        No operator profile?{" "}
        <Link
          href="/register"
          className="text-strix-primary dark:text-strix-cyan hover:underline font-medium"
        >
          Request clearance
        </Link>
      </p>

      {/* Security notice */}
      <div className="border-t border-[var(--strix-border)] pt-4">
        <p className="text-[10px] text-[var(--strix-text-muted)] text-center leading-relaxed">
          All sessions are encrypted with AES-256. Unauthorized access attempts
          are logged and reported to STRIX SENTINEL command.
        </p>
      </div>
    </div>
  )
}
