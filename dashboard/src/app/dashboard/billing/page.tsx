"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth";
import { billing, Subscription } from "@/lib/api";
import { Check } from "lucide-react";

const plans = [
  {
    id: "free",
    name: "Free",
    price: "$0",
    period: "forever",
    minutes: 60,
    features: [
      "60 minutes/month",
      "REST API access",
      "1 API key",
      "Community support",
    ],
  },
  {
    id: "pro",
    name: "Pro",
    price: "$29",
    period: "/month",
    minutes: 1000,
    features: [
      "1,000 minutes/month",
      "Real-time WebSocket streaming",
      "Unlimited API keys",
      "Speaker diarization",
      "PII redaction",
      "Priority support",
    ],
    popular: true,
  },
  {
    id: "enterprise",
    name: "Enterprise",
    price: "Custom",
    period: "",
    minutes: -1,
    features: [
      "Unlimited minutes",
      "Dedicated GPU instances",
      "Custom models & vocabulary",
      "SSO / SAML",
      "SLA guarantee",
      "Dedicated support",
    ],
  },
];

export default function BillingPage() {
  const { getToken } = useAuth();
  const [subscription, setSubscription] = useState<Subscription | null>(null);

  useEffect(() => {
    async function load() {
      const token = await getToken();
      if (token) {
        try {
          const data = await billing.subscription(token);
          setSubscription(data);
        } catch {
          // API not connected
        }
      }
    }
    load();
  }, [getToken]);

  async function handleSelectPlan(planId: string) {
    if (planId === "enterprise") {
      window.open("mailto:sales@aavaaz.dev?subject=Enterprise Plan", "_blank");
      return;
    }
    const token = await getToken();
    if (token) {
      try {
        const { url } = await billing.createCheckout(token, planId);
        window.location.href = url;
      } catch {
        // handle error
      }
    }
  }

  async function handleManageBilling() {
    const token = await getToken();
    if (token) {
      try {
        const { url } = await billing.createPortalSession(token);
        window.location.href = url;
      } catch {
        // handle error
      }
    }
  }

  return (
    <div className="space-y-8">
      <div className="flex justify-between items-start">
        <div>
          <h1 className="text-3xl font-bold">Billing</h1>
          <p className="text-muted-foreground mt-1">
            Manage your subscription and payment
          </p>
        </div>
        {subscription && (
          <button
            onClick={handleManageBilling}
            className="rounded-md border px-4 py-2 text-sm hover:bg-accent transition-colors"
          >
            Manage Billing
          </button>
        )}
      </div>

      {/* Current plan info */}
      {subscription && (
        <div className="rounded-lg border bg-card p-6">
          <div className="flex justify-between items-center">
            <div>
              <p className="text-sm text-muted-foreground">Current Plan</p>
              <p className="text-xl font-bold capitalize">
                {subscription.plan}
              </p>
            </div>
            <div className="text-right">
              <p className="text-sm text-muted-foreground">
                Next billing date
              </p>
              <p className="font-medium">
                {new Date(subscription.current_period_end).toLocaleDateString()}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Plans grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {plans.map((plan) => (
          <div
            key={plan.id}
            className={`rounded-lg border p-6 flex flex-col ${
              plan.popular ? "border-primary ring-1 ring-primary" : ""
            }`}
          >
            {plan.popular && (
              <span className="text-xs font-medium text-primary mb-2">
                Most Popular
              </span>
            )}
            <h3 className="text-xl font-bold">{plan.name}</h3>
            <div className="mt-2">
              <span className="text-3xl font-bold">{plan.price}</span>
              <span className="text-muted-foreground">{plan.period}</span>
            </div>

            <ul className="mt-6 space-y-3 flex-1">
              {plan.features.map((feature) => (
                <li key={feature} className="flex items-start gap-2 text-sm">
                  <Check className="h-4 w-4 text-primary mt-0.5 shrink-0" />
                  {feature}
                </li>
              ))}
            </ul>

            <button
              onClick={() => handleSelectPlan(plan.id)}
              className={`mt-6 w-full rounded-md px-4 py-2.5 text-sm font-medium transition-colors ${
                plan.popular
                  ? "bg-primary text-primary-foreground hover:bg-primary/90"
                  : "border hover:bg-accent"
              }`}
            >
              {plan.id === "enterprise"
                ? "Contact Sales"
                : subscription?.plan === plan.id
                ? "Current Plan"
                : "Select Plan"}
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
