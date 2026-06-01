'use client';

import React, { useState } from 'react';
import { useForm } from 'react-hook-form';
import { useRouter } from 'next/navigation';
import { Loader2, AlertCircle, Key, ArrowRight, Scan, Terminal, Cpu } from 'lucide-react';
import { toast } from 'sonner';
import AppLogo from '@/components/ui/AppLogo';

interface SignupFormData {
  fullName: string;
  email: string;
  code: string;
  username: string;
  password: string;
  apiKeyMode: 'platform' | 'own';
  ownApiKey?: string;
  agreeToTerms: boolean;
}

interface SignupFormProps {
  onSwitchToLogin: () => void;
}

export default function SignupForm({ onSwitchToLogin }: SignupFormProps) {
  const router = useRouter();
  const [step, setStep] = useState<'details' | 'otp' | 'profile'>('details');
  const [isLoading, setIsLoading] = useState(false);
  const [authError, setAuthError] = useState('');

  const {
    register,
    handleSubmit,
    watch,
    formState: { errors },
  } = useForm<SignupFormData>({
    defaultValues: {
      fullName: '',
      email: '',
      code: '',
      username: '',
      password: '',
      apiKeyMode: 'platform',
      agreeToTerms: false,
    },
  });

  const apiKeyMode = watch('apiKeyMode');
  const email = watch('email');

  const onSendOtp = async (data: SignupFormData) => {
    setIsLoading(true);
    setAuthError('');
    try {
      const res = await fetch('http://localhost:8000/api/auth/send-otp', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: data.email }),
      });
      const resData = await res.json();
      if (!res.ok) throw new Error(resData.detail || 'Failed to generate auth sequence');
      
      toast.success(`Verification sequence sent to ${data.email}`, { className: 'bg-black border-cyan-500 text-cyan-400 font-mono' });
      setStep('otp');
    } catch (err: any) {
      setAuthError(err.message || 'System connection error');
    } finally {
      setIsLoading(false);
    }
  };

  const onVerifyOtp = async (data: SignupFormData) => {
    setIsLoading(true);
    setAuthError('');
    try {
      const res = await fetch('http://localhost:8000/api/auth/verify-otp', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: data.email, code: data.code }),
      });
      const resData = await res.json();
      if (!res.ok) throw new Error(resData.detail || 'Invalid or expired sequence');
      
      toast.success(`Identity Verified. Establishing profile access...`, { className: 'bg-black border-cyan-500 text-cyan-400 font-mono' });
      setStep('profile');
    } catch (err: any) {
      setAuthError(err.message || 'Verification sequence failed');
    } finally {
      setIsLoading(false);
    }
  };

  const onCompleteProfile = async (data: SignupFormData) => {
    setIsLoading(true);
    setAuthError('');
    try {
      const res = await fetch('http://localhost:8000/api/profile', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          username: data.username, 
          password: data.password,
          full_name: data.fullName
        }),
      });
      const resData = await res.json();
      if (!res.ok) throw new Error(resData.detail || 'Failed to initialize profile');
      
      toast.success(`Profile Initialized. Welcome, ${data.username}`, { className: 'bg-black border-cyan-500 text-cyan-400 font-mono' });
      setTimeout(() => {
        window.location.assign('/chat-interface');
      }, 800);
    } catch (err: any) {
      setAuthError(err.message || 'Profile initialization sequence failed');
    } finally {
      setIsLoading(false);
    }
  };

  const handleGoogleSignup = async () => {
    try {
      const res = await fetch('http://localhost:8000/api/google/auth-url');
      const data = await res.json();
      if (!data.auth_url) {
        toast.info(data.message ?? 'Google uplink not established', { className: 'bg-black border-cyan-500 text-cyan-400 font-mono' });
        return;
      }
      window.open(data.auth_url, '_blank', 'noopener,noreferrer');
    } catch (error) {
      console.warn('Failed to start Google sign-up:', error);
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
            <Cpu className="text-cyan-400 w-6 h-6" />
          </div>
          <h2 className="text-2xl font-bold tracking-widest text-cyan-50 mb-2 uppercase drop-shadow-[0_0_8px_rgba(0,255,255,0.5)]">
            Entity Reg
          </h2>
          <p className="text-xs font-mono text-cyan-400/70 tracking-widest uppercase">
            Initialize new autonomous agent
          </p>
        </div>

        {/* Google SSO */}
        <button
          type="button"
          onClick={handleGoogleSignup}
          className="w-full flex items-center justify-center gap-3 px-4 py-3 rounded-xl border border-cyan-500/20 bg-cyan-950/20 hover:bg-cyan-900/30 hover:border-cyan-400/50 transition-all duration-300 text-sm font-mono text-cyan-100 mb-6 shadow-[0_0_10px_rgba(0,255,255,0.0)] hover:shadow-[0_0_15px_rgba(0,255,255,0.2)] uppercase tracking-wider relative group"
        >
          <div className="absolute inset-0 bg-cyan-400/5 scale-x-0 group-hover:scale-x-100 transition-transform origin-left rounded-xl" />
          <svg width="18" height="18" viewBox="0 0 18 18" fill="none" className="relative z-10 opacity-80 group-hover:opacity-100 transition-opacity">
            <path d="M17.64 9.2c0-.637-.057-1.251-.164-1.84H9v3.481h4.844c-.209 1.125-.843 2.078-1.796 2.717v2.258h2.908c1.702-1.567 2.684-3.874 2.684-6.615z" fill="#0ff"/>
            <path d="M9 18c2.43 0 4.467-.806 5.956-2.18l-2.908-2.259c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332C2.438 15.983 5.482 18 9 18z" fill="#0ff"/>
            <path d="M3.964 10.71c-.18-.54-.282-1.117-.282-1.71s.102-1.17.282-1.71V4.958H.957C.347 6.173 0 7.548 0 9s.348 2.827.957 4.042l3.007-2.332z" fill="#0ff"/>
            <path d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0 5.482 0 2.438 2.017.957 4.958L3.964 6.29C4.672 4.163 6.656 3.58 9 3.58z" fill="#0ff"/>
          </svg>
          <span className="relative z-10">Sync with Google</span>
        </button>

        <div className="flex items-center gap-3 mb-6 opacity-60">
          <div className="flex-1 h-px bg-gradient-to-r from-transparent via-cyan-500/50 to-transparent" />
          <span className="text-[10px] font-mono text-cyan-400 uppercase tracking-widest">Manual Entry</span>
          <div className="flex-1 h-px bg-gradient-to-r from-transparent via-cyan-500/50 to-transparent" />
        </div>

        {authError && (
          <div className="flex items-start gap-2.5 p-3 rounded-lg bg-red-950/50 border border-red-500/50 mb-5 animate-in slide-in-from-top-2">
            <AlertCircle size={15} className="text-red-400 shrink-0 mt-0.5" />
            <p className="text-xs font-mono text-red-400 uppercase tracking-wider">{authError}</p>
          </div>
        )}

        <form onSubmit={
          step === 'details' ? handleSubmit(onSendOtp) : 
          step === 'otp' ? handleSubmit(onVerifyOtp) : 
          handleSubmit(onCompleteProfile)
        } className="space-y-5">
          {/* STEP 1: Details Entry */}
          <div className={`transition-all duration-300 ${step !== 'details' ? 'opacity-30 pointer-events-none blur-[1px] hidden' : 'opacity-100'} space-y-5`}>
            {/* Full name */}
            <div>
              <label className="block text-xs font-mono text-cyan-400/80 mb-2 uppercase tracking-widest" htmlFor="signup-name">
                [ ENTITY DESIGNATION ]
              </label>
              <input
                id="signup-name"
                type="text"
                autoComplete="name"
                {...register('fullName', {
                  required: 'Designation required',
                  minLength: { value: 2, message: 'Must be >2 chars' },
                })}
                className={`w-full px-4 py-3 rounded-lg border bg-black/50 text-cyan-100 text-sm font-mono placeholder:text-cyan-800/60 focus:outline-none focus:ring-1 focus:ring-cyan-500/50 transition-all ${
                  errors.fullName ? 'border-red-500/50 shadow-[0_0_10px_rgba(255,0,0,0.2)]' : 'border-cyan-500/30 focus:border-cyan-400 focus:shadow-[0_0_15px_rgba(0,255,255,0.2)]'
                }`}
                placeholder="Operator Sigma"
              />
              {errors.fullName && <p className="mt-2 text-[10px] font-mono uppercase text-red-400">{errors.fullName.message}</p>}
            </div>

            {/* Email */}
            <div>
              <label className="block text-xs font-mono text-cyan-400/80 mb-2 uppercase tracking-widest" htmlFor="signup-email">
                [ IDENTITY URI ]
              </label>
              <input
                id="signup-email"
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

            {/* API Key mode */}
            <div>
              <label className="block text-xs font-mono text-cyan-400/80 mb-2 uppercase tracking-widest">
                [ NEURAL NETWORK ACCESS ]
              </label>
              <div className="space-y-2">
                {[
                  { value: 'platform', label: 'SYS_MANAGED_KEY', description: 'Billed to platform quota' },
                  { value: 'own', label: 'INJECT_CUSTOM_KEY', description: 'Override with external token' },
                ].map((opt) => (
                  <label
                    key={`apimode-${opt.value}`}
                    className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-all ${
                      apiKeyMode === opt.value
                        ? 'border-cyan-400 bg-cyan-900/30 shadow-[0_0_15px_rgba(0,255,255,0.15)]'
                        : 'border-cyan-900/50 bg-black/40 hover:border-cyan-500/50'
                    }`}
                  >
                    <input
                      type="radio"
                      value={opt.value}
                      {...register('apiKeyMode')}
                      className="mt-0.5 text-cyan-500 focus:ring-cyan-500/30 accent-cyan-400"
                    />
                    <div>
                      <p className="text-xs font-mono font-bold text-cyan-100 uppercase tracking-widest">{opt.label}</p>
                      <p className="text-[10px] font-mono text-cyan-500/70 mt-1 uppercase tracking-wider">{opt.description}</p>
                    </div>
                  </label>
                ))}
              </div>

              {/* Own API key input */}
              {apiKeyMode === 'own' && (
                <div className="mt-3 animate-in slide-in-from-top-2 fade-in duration-200">
                  <div className="relative">
                    <Key size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-cyan-600" />
                    <input
                      id="signup-apikey"
                      type="password"
                      {...register('ownApiKey')}
                      placeholder="sk-..."
                      className="w-full pl-9 pr-4 py-3 rounded-lg border border-cyan-500/30 bg-black/50 text-cyan-100 text-sm font-mono placeholder:text-cyan-800/50 focus:outline-none focus:ring-1 focus:ring-cyan-400 focus:shadow-[0_0_15px_rgba(0,255,255,0.2)] transition-all"
                    />
                  </div>
                  <p className="text-[10px] font-mono text-cyan-500/60 mt-2 uppercase tracking-widest">
                    Token encrypted in cold storage.
                  </p>
                </div>
              )}
            </div>

            {/* Terms */}
            <div>
              <div className="flex items-start gap-3">
                <input
                  id="agree-terms"
                  type="checkbox"
                  {...register('agreeToTerms', { required: 'Consent required' })}
                  className="w-4 h-4 mt-0.5 rounded border-cyan-500/50 bg-black text-cyan-500 focus:ring-cyan-500/30 cursor-pointer accent-cyan-500"
                />
                <label htmlFor="agree-terms" className="text-[10px] font-mono text-cyan-400/70 uppercase tracking-widest cursor-pointer leading-relaxed select-none">
                  Acknowledge <span className="text-cyan-400 hover:text-cyan-300 hover:drop-shadow-[0_0_5px_rgba(0,255,255,0.8)] cursor-pointer transition-all">Directives</span> & <span className="text-cyan-400 hover:text-cyan-300 hover:drop-shadow-[0_0_5px_rgba(0,255,255,0.8)] cursor-pointer transition-all">Privacy Protocols</span>
                </label>
              </div>
              {errors.agreeToTerms && <p className="mt-2 text-[10px] font-mono text-red-400 uppercase">{errors.agreeToTerms.message}</p>}
            </div>
          </div>

          {/* STEP 2: OTP Verification */}
          {step === 'otp' && (
            <div className="animate-in slide-in-from-bottom-4 fade-in duration-300 space-y-6">
              <div className="p-4 rounded-lg bg-cyan-500/10 border border-cyan-500/30 flex items-center gap-3">
                <Terminal size={20} className="text-cyan-400" />
                <p className="text-[10px] font-mono text-cyan-100 uppercase tracking-wider leading-relaxed">
                  Verification sequence dispatched. Enter code to establish secure uplink.
                </p>
              </div>

              <div>
                <label className="block text-xs font-mono text-cyan-400/80 mb-2 uppercase tracking-widest text-center" htmlFor="signup-otp">
                  :: [ AUTHENTICATION SEQUENCE ]
                </label>
                <input
                  id="signup-otp"
                  type="text"
                  maxLength={6}
                  {...register('code', {
                    required: 'Sequence required',
                    minLength: { value: 6, message: 'Incomplete sequence' },
                  })}
                  className="w-full bg-black/60 border border-cyan-500/50 rounded-lg py-4 text-center text-2xl font-mono tracking-[0.5em] text-cyan-400 focus:outline-none focus:ring-1 focus:ring-cyan-400 focus:shadow-[0_0_20px_rgba(0,255,255,0.3)] transition-all placeholder:text-cyan-900"
                  placeholder="000000"
                />
                {errors.code && <p className="mt-2 text-center text-[10px] font-mono uppercase text-red-400">{errors.code.message}</p>}
              </div>

              <button
                type="button"
                onClick={() => setStep('details')}
                className="w-full text-[10px] font-mono text-cyan-500/60 uppercase tracking-widest hover:text-cyan-400 transition-colors text-center"
              >
                ABORT // RE-ENTER IDENTITY
              </button>
            </div>
          )}

          {/* STEP 3: Profile Setup */}
          {step === 'profile' && (
            <div className="animate-in slide-in-from-bottom-4 fade-in duration-300 space-y-6">
              <div className="p-4 rounded-lg bg-green-500/10 border border-green-500/30 flex items-center gap-3">
                <Scan size={20} className="text-green-400" />
                <p className="text-[10px] font-mono text-green-100 uppercase tracking-wider leading-relaxed">
                  Identity Verified. Establish your system credentials to finalize initialization.
                </p>
              </div>

              <div className="space-y-4">
                {/* Username */}
                <div>
                  <label className="block text-xs font-mono text-cyan-400/80 mb-2 uppercase tracking-widest" htmlFor="profile-username">
                    [ SYSTEM USERNAME ]
                  </label>
                  <input
                    id="profile-username"
                    type="text"
                    {...register('username', {
                      required: 'Username required',
                      minLength: { value: 3, message: 'Must be >3 chars' },
                    })}
                    className="w-full px-4 py-3 rounded-lg border border-cyan-500/30 bg-black/50 text-cyan-100 text-sm font-mono placeholder:text-cyan-800/60 focus:outline-none focus:ring-1 focus:ring-cyan-500/50 transition-all focus:border-cyan-400"
                    placeholder="Neo_Operator"
                  />
                  {errors.username && <p className="mt-1 text-[10px] font-mono uppercase text-red-400">{errors.username.message}</p>}
                </div>

                {/* Password */}
                <div>
                  <label className="block text-xs font-mono text-cyan-400/80 mb-2 uppercase tracking-widest" htmlFor="profile-password">
                    [ ACCESS KEY_PHRASE ]
                  </label>
                  <input
                    id="profile-password"
                    type="password"
                    {...register('password', {
                      required: 'Access key required',
                      minLength: { value: 6, message: 'Must be >6 chars' },
                    })}
                    className="w-full px-4 py-3 rounded-lg border border-cyan-500/30 bg-black/50 text-cyan-100 text-sm font-mono placeholder:text-cyan-800/60 focus:outline-none focus:ring-1 focus:ring-cyan-500/50 transition-all focus:border-cyan-400"
                    placeholder="••••••••"
                  />
                  {errors.password && <p className="mt-1 text-[10px] font-mono uppercase text-red-400">{errors.password.message}</p>}
                </div>
              </div>
            </div>
          )}

          {/* Submit Button */}
          <button
            type="submit"
            disabled={isLoading}
            className="w-full relative group overflow-hidden px-6 py-4 rounded-xl bg-cyan-500 text-black font-mono font-bold text-sm tracking-widest uppercase transition-all hover:bg-cyan-400 active:scale-95 disabled:opacity-50 disabled:pointer-events-none shadow-[0_0_20px_rgba(0,255,255,0.3)]"
          >
            <div className="absolute inset-0 bg-white/20 translate-x-[-100%] group-hover:translate-x-[100%] transition-transform duration-700 skew-x-12" />
            <div className="flex items-center justify-center gap-2">
              {isLoading ? (
                <Loader2 size={18} className="animate-spin" />
              ) : step === 'details' ? (
                <><Cpu size={18} /> GENERATE SEQUENCE</>
              ) : step === 'otp' ? (
                <><Scan size={18} /> VERIFY & EXECUTE</>
              ) : (
                <><ArrowRight size={18} /> COMPLETE INITIALIZATION</>
              )}
            </div>
          </button>
        </form>

        <p className="text-center text-xs font-mono text-cyan-500/60 mt-8 uppercase tracking-widest">
          Existing Entity?{' '}
          <button
            onClick={onSwitchToLogin}
            className="text-cyan-400 hover:text-cyan-300 font-bold transition-colors relative after:absolute after:-bottom-1 after:left-0 after:h-[1px] after:w-full after:bg-cyan-400 after:scale-x-0 hover:after:scale-x-100 after:transition-transform after:origin-left drop-shadow-[0_0_5px_rgba(0,255,255,0.5)]"
          >
            Authenticate
          </button>
        </p>
      </div>
    </div>
  );
}
