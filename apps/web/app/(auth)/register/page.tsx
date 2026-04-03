"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
import Link from "next/link"
import { useAuthStore } from "@/stores/auth-store"
import { Shield, Eye, EyeOff, Loader2 } from "lucide-react"

export default function RegisterPage() {
  const router = useRouter()
  const { register } = useAuthStore()
  const [designation, setDesignation] = useState("")
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [confirmPassword, setConfirmPassword] = useState("")
  const [showPassword, setShowPassword] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError("")

    if (password !== confirmPassword) {
      setError("Access keys do not match")
      return
    }

    if (password.length < 8) {
      setError("Access key must be at least 8 characters")
      return
    }

    setLoading(true)

    try {
      const success = await register(designation, email, password)
      if (success) {
        router.push("/")
      } else {
        setError("Registration failed")
      }
    } catch {
      setError("System error during registration")
    } finally {
      setLoading(false)
    }
  }

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
          Operator Registration
        </h2>
        <p className="text-sm text-[var(--strix-text-muted)]">
          Request clearance for the STRIX sentinel network
        </p>
      </div>

      {/* Form */}
      <form onSubmit={handleSubmit} className="space-y-5">
        {/* Designation */}
        <div className="space-y-2">
          <label className="text-xs font-medium text-[var(--strix-text)] uppercase tracking-wider">
            Operator Designation
          </label>
          <input
            type="text"
            value={designation}
            onChange={(e) => setDesignation(e.target.value)}
            placeholder="Sentinel-Alpha-B"
            required
            className="w-full rounded-lg border border-[var(--strix-border)] bg-[var(--strix-bg-surface)] px-4 py-3 text-sm text-[var(--strix-text)] placeholder:text-[var(--strix-text-muted)] outline-none transition-colors focus:border-strix-primary dark:focus:border-strix-cyan focus:ring-1 focus:ring-strix-primary/20 dark:focus:ring-strix-cyan/20"
          />
        </div>

        {/* Network Protocol (email) */}
        <div className="space-y-2">
          <label className="text-xs font-medium text-[var(--strix-text)] uppercase tracking-wider">
            Network Protocol
          </label>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="alpha@strix.intel"
            required
            className="w-full rounded-lg border border-[var(--strix-border)] bg-[var(--strix-bg-surface)] px-4 py-3 text-sm text-[var(--strix-text)] placeholder:text-[var(--strix-text-muted)] outline-none transition-colors focus:border-strix-primary dark:focus:border-strix-cyan focus:ring-1 focus:ring-strix-primary/20 dark:focus:ring-strix-cyan/20"
          />
        </div>

        {/* Access Key */}
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

        {/* Confirm Access Key */}
        <div className="space-y-2">
          <label className="text-xs font-medium text-[var(--strix-text)] uppercase tracking-wider">
            Confirm Access Key
          </label>
          <input
            type="password"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            placeholder="••••••••••••"
            required
            className="w-full rounded-lg border border-[var(--strix-border)] bg-[var(--strix-bg-surface)] px-4 py-3 text-sm text-[var(--strix-text)] placeholder:text-[var(--strix-text-muted)] outline-none transition-colors focus:border-strix-primary dark:focus:border-strix-cyan focus:ring-1 focus:ring-strix-primary/20 dark:focus:ring-strix-cyan/20"
          />
        </div>

        {/* Clearance Level */}
        <div className="space-y-2">
          <label className="text-xs font-medium text-[var(--strix-text)] uppercase tracking-wider">
            Clearance Level
          </label>
          <select className="w-full rounded-lg border border-[var(--strix-border)] bg-[var(--strix-bg-surface)] px-4 py-3 text-sm text-[var(--strix-text)] outline-none transition-colors focus:border-strix-primary dark:focus:border-strix-cyan">
            <option>Analyst — Tier 1</option>
            <option>Operator — Tier 2</option>
            <option>Architect — Tier 3</option>
            <option>Commander — Tier 4</option>
          </select>
        </div>

        {/* Error */}
        {error && (
          <div className="rounded-lg bg-red-500/10 border border-red-500/20 px-4 py-3 text-xs text-red-500">
            {error}
          </div>
        )}

        {/* Terms */}
        <label className="flex items-start gap-2 text-xs text-[var(--strix-text-muted)] cursor-pointer">
          <input
            type="checkbox"
            required
            className="mt-0.5 rounded border-[var(--strix-border)] text-strix-primary focus:ring-strix-primary/20"
          />
          <span>
            I acknowledge the STRIX operational protocols and consent to
            continuous biometric monitoring during active sessions.
          </span>
        </label>

        {/* Submit */}
        <button
          type="submit"
          disabled={loading}
          className="w-full rounded-lg bg-strix-primary dark:bg-strix-cyan py-3 text-sm font-semibold text-white dark:text-strix-bg-dark tracking-wider uppercase transition-all hover:opacity-90 disabled:opacity-50 flex items-center justify-center gap-2"
        >
          {loading ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              Processing clearance...
            </>
          ) : (
            "Request Clearance"
          )}
        </button>
      </form>

      {/* Login link */}
      <p className="text-center text-xs text-[var(--strix-text-muted)]">
        Already registered?{" "}
        <Link
          href="/login"
          className="text-strix-primary dark:text-strix-cyan hover:underline font-medium"
        >
          Authenticate
        </Link>
      </p>
    </div>
  )
}
