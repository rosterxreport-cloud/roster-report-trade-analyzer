# NBA availability in public releases

The established model's full conditional forecasts remain in private immutable source archives. Public basic projection and distribution lists pass through the same current official NBA report used for slate eligibility before publication. Confirmed Out, inactive and doubtful players are excluded; remaining rows carry availability labels, and missing/unsubmitted team reports remain unverified. Forecast values, statlines, scoring, model parameters and source hashes are not recalibrated.

On November 17, the official 9:45 AM Eastern injury report listed Kawhi Leonard (TOR) and Jusuf Nurkic (UTA) Out. Neither was present in the eligible current DFS pool, but both remained in the general conditional projections. The worker now captures the official report before publishing those public lists and applies exclusions to basic and distribution artifacts. The projections API and page expose availability for remaining rows. The private model archive retains the original outputs.

Two focused tests verify Out-player removal, Unicode name normalization, unchanged remaining projections, unchanged raw source rows and fail-closed labels for unverified teams. The full application suite passed after the release change. Preview refresh/readback must be verified before claiming the currently served artifact is filtered.
