'use client';

import React, { useState } from 'react';
import { useForm } from 'react-hook-form';
import { useRouter } from 'next/navigation';
import { Loader2, AlertCircle, ArrowRight, Scan, Terminal } from 'lucide-react';
import { toast } from 'sonner';
import AppLogo from '@/components/ui/AppLogo';

interface LoginFormData {
  email: string;
  code: string;
  rememberMe: boolean;
}

interface LoginFormProps {
  onSwitchToSignup: () => void;
}

export default function LoginForm({ onSwitchToSignup }: LoginFormProps) {
  const router = useRouter();
  const [step, setStep] = useState<'email' | 'otp'>('email');
  const [isLoading, setIsLoading] = useState(false);
  const [authError, setAuthError] = useState('');

  const {
    register,
    handleSubmit,
    watch,
    formState: { errors },
  } = useForm<LoginFormData>({
    defaultValues: { email: '', code: '', rememberMe: false },
  });

  const email = watch('email');

  const onSendOtp = async (data: LoginFormData) => {
    setIsLoading(true);
    setAuthError('');
    try {
      const res = await fetch('http://localhost:8000/api/auth/send-otp', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: data.email }),
      });
      const resData = await res.json();
      if (!res.ok) throw new Error(resData.detail || 'Failed to send OTP');
      
      toast.success(`Encrypted sequence sent to ${data.email}`, { className: 'bg-black border-cyan-500 text-cyan-400 font-mono' });
      setStep('otp');
    } catch (err: any) {
      setAuthError(err.message || 'System connection error');
    } finally {
      setIsLoading(false);
    }
  };

  const onVerifyOtp = async (data: LoginFormData) => {
    setIsLoading(true);
    setAuthError('');
    try {
      const res = await fetch('http://localhost:8000/api/auth/verify-otp', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: data.email, code: data.code }),
      });
      const resData = await res.json();
      if (!res.ok) throw new Error(resData.detail || 'Invalid authentication sequence');
      
      toast.success('Access Granted. Initializing workspace...', { className: 'bg-black border-cyan-500 text-cyan-400 font-mono' });
      setTimeout(() => {
        window.location.assign('/chat-interface');
      }, 800);
    } catch (err: any) {
      setAuthError(err.message || 'Verification sequence failed');
    } finally {
      setIsLoading(false);
    }
  };

  const handleGoogleSignin = async () => {
    try {
      const res = await fetch('http://localhost:8000/api/google/auth-url');
      const data = await res.json();
      if (!data.auth_url) {
        toast.info(data.message ?? 'Google uplink not established', { className: 'bg-black border-cyan-500 text-cyan-400 font-mono' });
        return;
      }
      window.open(data.auth_url, '_blank', 'noopener,noreferrer');
    } catch (error) {
      console.error('Failed to start Google sign-in:', error);
      toast.error('Google uplink failure', { className: 'bg-black border-red-500 text-red-400 font-mono' });
    }
  };

  return (
    <div className="animate-fade-in relative z-10 w-full max-w-md mx-auto">
      {/* Cyberpunk Grid Background Overlay */}
      <div className="absolute inset-0 bg-[linear-gradient(rgba(0,255,255,0.03)_1px,transparent_1px),linear-gradient(90deg,rgba(0,255,255,0.03)_1px,transparent_1px)] bg-[size:20px_20px] -z-10 pointer-events-none opacity-50" />
      
      <div className="p-8 rounded-2xl bg-black/80 backdrop-blur-xl border border-cyan-500/30 shadow-[0_0_30px_rgba(0,255,255,0.05)] relative overflow-hidden">
        {/* Scanning Line Animation */}
        <div className="absolute top-0 left-0 w-full h-[2px] bg-cyan-400/50 shadow-[0_0_10px_#0ff] animate-scan-line pointer-events-none opacity-50" />
        
        {/* Header */}
        <div className="mb-8 text-center flex flex-col items-center">
          <div className="w-12 h-12 bg-cyan-950/50 rounded-xl border border-cyan-500/50 flex items-center justify-center mb-4 shadow-[0_0_15px_rgba(0,255,255,0.2)]">
            <Terminal className="text-cyan-400 w-6 h-6" />
          </div>
          <h2 className="text-2xl font-bold tracking-widest text-cyan-50 mb-2 uppercase drop-shadow-[0_0_8px_rgba(0,255,255,0.5)]">
            System Auth
          </h2>
          <p className="text-xs font-mono text-cyan-400/70 tracking-widest uppercase">
            Initialize agent workspace
          </p>
        </div>

        {/* Google SSO */}
        <button
          type="button"
          onClick={handleGoogleSignin}
          className="w-full flex items-center justify-center gap-3 px-4 py-3 rounded-xl border border-cyan-500/20 bg-cyan-950/20 hover:bg-cyan-900/30 hover:border-cyan-400/50 transition-all duration-300 text-sm font-mono text-cyan-100 mb-6 shadow-[0_0_10px_rgba(0,255,255,0.0)] hover:shadow-[0_0_15px_rgba(0,255,255,0.2)] uppercase tracking-wider relative group"
        >
          <div className="absolute inset-0 bg-cyan-400/5 scale-x-0 group-hover:scale-x-100 transition-transform origin-left rounded-xl" />
          <svg width="18" height="18" viewBox="0 0 18 18" fill="none" className="relative z-10 opacity-80 group-hover:opacity-100 transition-opacity">
            <path d="M17.64 9.2c0-.637-.057-1.251-.164-1.84H9v3.481h4.844c-.209 1.125-.843 2.078-1.796 2.717v2.258h2.908c1.702-1.567 2.684-3.874 2.684-6.615z" fill="#0ff"/>
            <path d="M9 18c2.43 0 4.467-.806 5.956-2.18l-2.908-2.259c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332C2.438 15.983 5.482 18 9 18z" fill="#0ff"/>
            <path d="M3.964 10.71c-.18-.54-.282-1.117-.282-1.71s.102-1.17.282-1.71V4.958H.957C.347 6.173 0 7.548 0 9s.348 2.827.957 4.042l3.007-2.332z" fill="#0ff"/>
            <path d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0 5.482 0 2.438 2.017.957 4.958L3.964 6.29C4.672 4.163 6.656 3.58 9 3.58z" fill="#0ff"/>
          </svg>
          <span className="relative z-10">Uplink via Google</span>
        </button>

        <div className="flex items-center gap-3 mb-6 opacity-60">
          <div className="flex-1 h-px bg-gradient-to-r from-transparent via-cyan-500/50 to-transparent" />
          <span className="text-[10px] font-mono text-cyan-400 uppercase tracking-widest">Secondary Auth</span>
          <div className="flex-1 h-px bg-gradient-to-r from-transparent via-cyan-500/50 to-transparent" />
        </div>

        {authError && (
          <div className="flex items-start gap-2.5 p-3 rounded-lg bg-red-950/50 border border-red-500/50 mb-5 animate-in slide-in-from-top-2">
            <AlertCircle size={15} className="text-red-400 shrink-0 mt-0.5" />
            <p className="text-xs font-mono text-red-400 uppercase tracking-wider">{authError}</p>
          </div>
        )}

        <form onSubmit={step === 'email' ? handleSubmit(onSendOtp) : handleSubmit(onVerifyOtp)} className="space-y-5">
          <div className={`transition-all duration-300 ${step === 'otp' ? 'opacity-30 pointer-events-none blur-[1px]' : 'opacity-100'}`}>
            <label className="block text-xs font-mono text-cyan-400/80 mb-2 uppercase tracking-widest" htmlFor="login-email">
              [ IDENTITY URI ]
            </label>
            <input
              id="login-email"
              type="email"
              autoComplete="email"
              {...register('email', {
                required: 'Identity URI required',
                pattern: { value: /^[^\s@]+@[^\s@]+\.[^\s@]+$/, message: 'Invalid format' },
              })}
              className={`w-full px-4 py-3 rounded-lg border bg-black/50 text-cyan-100 text-sm font-mono placeholder:text-cyan-800/60 focus:outline-none focus:ring-1 focus:ring-cyan-500/50 transition-all ${
                errors.email ? 'border-red-500/50 shadow-[0_0_10px_rgba(255,0,0,0.2)]' : 'border-cyan-500/30 focus:border-cyan-400 focus:shadow-[0_0_15px_rgba(0,255,255,0.2)]'
              }`}
              placeholder="operator@sys.net"
            />
            {errors.email && <p className="mt-2 text-[10px] font-mono uppercase text-red-400">{errors.email.message}</p>}
          </div>

          {step === 'otp' && (
            <div className="animate-in slide-in-from-bottom-4 fade-in duration-300">
              <label className="block text-xs font-mono text-cyan-400/80 mb-2 uppercase tracking-widest flex items-center gap-2" htmlFor="login-code">
                <Scan size={14} className="text-cyan-400" /> [ AUTHENTICATION SEQUENCE ]
              </label>
              <input
                id="login-code"
                type="text"
                autoComplete="one-time-code"
                maxLength={6}
                {...register('code', {
                  required: 'Sequence required',
                  minLength: { value: 6, message: 'Sequence must be 6 digits' },
                })}
                className={`w-full px-4 py-3 rounded-lg border bg-cyan-950/20 text-cyan-50 text-center tracking-[0.5em] text-lg font-mono placeholder:text-cyan-900 placeholder:tracking-normal focus:outline-none focus:ring-1 focus:ring-cyan-400 transition-all ${
                  errors.code ? 'border-red-500/50 shadow-[0_0_10px_rgba(255,0,0,0.2)]' : 'border-cyan-400/50 focus:shadow-[0_0_20px_rgba(0,255,255,0.3)]'
                }`}
                placeholder="000000"
              />
              {errors.code && <p className="mt-2 text-[10px] font-mono text-red-400 text-center uppercase">{errors.code.message}</p>}
              <button
                type="button"
                onClick={() => { setStep('email'); setAuthError(''); }}
                className="mt-3 w-full text-[10px] font-mono text-cyan-500 hover:text-cyan-300 transition-colors text-center uppercase tracking-widest"
              >
                Abort &gt; Re-enter Identity
              </button>
            </div>
          )}

          <div className="flex items-center gap-3 pt-2">
            <input
              id="remember-me"
              type="checkbox"
              {...register('rememberMe')}
              className="w-4 h-4 rounded border-cyan-500/50 bg-black text-cyan-500 focus:ring-cyan-500/30 focus:ring-offset-0 cursor-pointer accent-cyan-500"
            />
            <label htmlFor="remember-me" className="text-xs font-mono text-cyan-400/60 uppercase tracking-widest cursor-pointer select-none">
              Maintain Connection
            </label>
          </div>

          <button
            type="submit"
            disabled={isLoading}
            className="group w-full flex items-center justify-center gap-3 px-4 py-3.5 rounded-lg bg-cyan-500/10 border border-cyan-400/50 hover:bg-cyan-400/20 text-cyan-300 font-mono text-sm tracking-widest uppercase transition-all duration-300 active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed hover:shadow-[0_0_20px_rgba(0,255,255,0.3)] overflow-hidden relative"
          >
            {/* Button scanning line */}
            <div className="absolute inset-0 bg-gradient-to-r from-transparent via-cyan-400/20 to-transparent translate-x-[-100%] group-hover:translate-x-[100%] transition-transform duration-1000" />
            
            {isLoading ? (
              <Loader2 size={16} className="animate-spin text-cyan-400 relative z-10" />
            ) : step === 'email' ? (
              <span className="flex items-center gap-2 relative z-10 text-cyan-100 drop-shadow-[0_0_5px_rgba(0,255,255,0.8)]">
                Request Sequence <ArrowRight size={16} className="group-hover:translate-x-1 transition-transform" />
              </span>
            ) : (
              <span className="relative z-10 text-cyan-100 drop-shadow-[0_0_5px_rgba(0,255,255,0.8)]">Verify & Execute</span>
            )}
          </button>
        </form>
      </div>

      <p className="text-center text-xs font-mono text-cyan-500/60 mt-8 uppercase tracking-widest">
        Unregistered Entity?{' '}
        <button
          onClick={onSwitchToSignup}
          className="text-cyan-400 hover:text-cyan-300 font-bold transition-colors relative after:absolute after:-bottom-1 after:left-0 after:h-[1px] after:w-full after:bg-cyan-400 after:scale-x-0 hover:after:scale-x-100 after:transition-transform after:origin-left drop-shadow-[0_0_5px_rgba(0,255,255,0.5)]"
        >
          Initialize Account
        </button>
      </p>
    </div>
  );
}

