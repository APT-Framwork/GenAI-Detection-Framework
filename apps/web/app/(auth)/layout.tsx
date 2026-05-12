import { Toaster } from "@/components/layout/toaster"
import { CavixLogo } from "@/components/layout/cavix-logo"

export default function AuthLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <div className="min-h-screen flex"><Toaster />
      {/* Left: Branding Panel */}
      <div className="hidden lg:flex lg:w-1/2 bg-gradient-to-br from-[#0A1628] via-[#0D1F3C] to-[#0B0E14] relative overflow-hidden flex-col items-center justify-center p-12">
        {/* Glow effects */}
        <div className="absolute top-1/4 left-1/4 w-64 h-64 bg-strix-cyan/10 rounded-full blur-[100px]" />
        <div className="absolute bottom-1/3 right-1/4 w-48 h-48 bg-strix-purple/10 rounded-full blur-[80px]" />

        {/* Content */}
        <div className="relative z-10 text-center space-y-8">
          {/* Logo */}
          <div className="flex flex-col items-center gap-2 mb-6">
            <CavixLogo width={240} color="#00F2FF" />
            <p className="text-xs text-strix-cyan/60 tracking-[0.3em] uppercase">
              Powered by the STRIX RL agent
            </p>
          </div>

          <div className="space-y-4 max-w-md">
            <h2 className="text-xl font-semibold text-white/90">
              Cyber Threat Intelligence Platform
            </h2>
            <p className="text-sm text-gray-400 leading-relaxed">
              Real-time threat detection, AI-powered attack analysis,
              and autonomous security orchestration driven by the STRIX
              reinforcement-learning agent.
            </p>
          </div>

          {/* Feature pills */}
          <div className="flex flex-wrap justify-center gap-2 mt-8">
            {[
              "Kill Chain Analysis",
              "STRIX RL Agent",
              "Live Topology",
              "Threat Intelligence",
            ].map((feature) => (
              <span
                key={feature}
                className="px-3 py-1.5 rounded-full text-[10px] font-medium tracking-wider text-strix-cyan/80 border border-strix-cyan/20 bg-strix-cyan/5"
              >
                {feature}
              </span>
            ))}
          </div>
        </div>

        {/* Grid pattern */}
        <div className="absolute inset-0 opacity-[0.03]"
          style={{
            backgroundImage: `linear-gradient(rgba(0,242,255,0.3) 1px, transparent 1px), linear-gradient(90deg, rgba(0,242,255,0.3) 1px, transparent 1px)`,
            backgroundSize: "40px 40px",
          }}
        />
      </div>

      {/* Right: Form */}
      <div className="flex-1 flex items-center justify-center p-8 bg-[var(--strix-bg)]">
        <div className="w-full max-w-md">
          {children}
        </div>
      </div>
    </div>
  )
}
