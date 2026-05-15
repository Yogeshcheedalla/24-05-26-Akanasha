import React, { Suspense } from 'react';
import { ThemeProvider } from '@/components/ThemeProvider';
import AuthScreen from './components/AuthScreen';
import { Toaster } from 'sonner';

export default function SignUpLoginPage() {
  return (
    <ThemeProvider>
      <Suspense fallback={null}>
        <AuthScreen />
      </Suspense>
      <Toaster position="bottom-right" />
    </ThemeProvider>
  );
}
