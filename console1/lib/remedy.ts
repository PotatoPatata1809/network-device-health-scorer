export const REMEDY: Record<string, string> = {
  hrStorageUsed: "Fail over to the peer device, restart the leaking process, confirm memory returns to normal.",
  hrProcessorLoad: "Find the process eating CPU; check for routing churn before restarting anything.",
  ifInErrors: "Check the cable and optics on the flagged port; replace the patch lead if errors keep climbing.",
  ifInOctets: "Confirm the traffic is expected; look for a loop before rate-limiting.",
  sysUpTime: "Check power and temperature logs; hold config changes until the device stays up.",
};
