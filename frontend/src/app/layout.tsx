import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'RealmCast — 3D Universe Builder',
  description: 'Upload room photos and explore them as a 3D universe',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-[#0a0a0a] text-white antialiased">
        {children}
      </body>
    </html>
  );
}
