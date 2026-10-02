"use client";

import { JobChrome } from "@/components/job-chrome";
import { JobProvider } from "@/components/job-provider";

export default function JobLayout({ children }: { children: React.ReactNode }) {
  return (
    <JobProvider>
      <JobChrome>{children}</JobChrome>
    </JobProvider>
  );
}
