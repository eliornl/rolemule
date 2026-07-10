/**
 * Official PostHog stub loader — preserved verbatim from legacy analytics.js.
 */
export function injectPostHogStub(): void {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  (function (t: Document, e: any) {
    let o: number;
    let n: number;
    let p: HTMLScriptElement;
    let r: HTMLScriptElement;
    if (!e.__SV) {
      window.posthog = e;
      e._i = [];
      e.init = function (
        i: unknown,
        s: { api_host: string },
        a?: string,
      ) {
        function g(target: Record<string, unknown>, event: string) {
          const parts = event.split('.');
          let tObj = target;
          let ev = event;
          if (parts.length === 2) {
            tObj = target[parts[0]] as Record<string, unknown>;
            ev = parts[1];
          }
          tObj[ev] = function (...args: unknown[]) {
            (tObj.push as (items: unknown[]) => void)([ev, ...args]);
          };
        }
        p = t.createElement('script');
        p.type = 'text/javascript';
        p.crossOrigin = 'anonymous';
        p.async = true;
        p.src = `${s.api_host.replace('.i.posthog.com', '-assets.i.posthog.com')}/static/array.js`;
        r = t.getElementsByTagName('script')[0];
        r.parentNode?.insertBefore(p, r);
        let u = e;
        let alias = a;
        if (alias !== undefined) {
          u = e[alias] = [];
        } else {
          alias = 'posthog';
        }
        u.people = u.people || [];
        u.toString = function (flag?: number) {
          let label = 'posthog';
          if (alias !== 'posthog') label += `.${alias}`;
          if (!flag) label += ' (stub)';
          return label;
        };
        u.people.toString = function () {
          return `${u.toString(1)}.people (stub)`;
        };
        const methods =
          'init capture register register_once register_for_session unregister unregister_for_session getFeatureFlag getFeatureFlagPayload isFeatureEnabled reloadFeatureFlags updateEarlyAccessFeatureEnrollment getEarlyAccessFeatures on onFeatureFlags onSessionId getSurveys getActiveMatchingSurveys renderSurvey canRenderSurvey getNextSurveyStep identify setPersonProperties group resetGroups setPersonPropertiesForFlags resetPersonPropertiesForFlags setGroupPropertiesForFlags resetGroupPropertiesForFlags reset get_distinct_id getGroups get_session_id get_session_replay_url alias set_config startSessionRecording stopSessionRecording sessionRecordingStarted captureException loadToolbar get_property getSessionProperty createPersonProfile opt_in_capturing opt_out_capturing has_opted_in_capturing has_opted_out_capturing clear_opt_in_out_capturing debug'.split(
            ' ',
          );
        for (o = 0; o < methods.length; o++) g(u, methods[o]);
        e._i.push([i, s, alias]);
      };
      e.__SV = 1;
    }
  })(document, window.posthog || []);
}
