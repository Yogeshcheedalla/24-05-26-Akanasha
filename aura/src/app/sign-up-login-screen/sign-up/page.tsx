import React, { Suspense } from 'react';
import { ThemeProvider } from '@/components/ThemeProvider';
import { Toaster } from 'sonner';
import AuthScreen from '../components/AuthScreen';

export default function SignUpPage() {
  return (
    <ThemeProvider>
      <Suspense fallback={null}>
        <AuthScreen initialMode="sign-up" />
      </Suspense>
      <Toaster position="bottom-right" />
    </ThemeProvider>
  );
}
