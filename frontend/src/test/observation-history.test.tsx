import {render,screen} from '@testing-library/react';
import {expect,it} from 'vitest';
import {ObservationBadge,HistoryNotice} from '@/components/common';
it('shows stale UP as missing observations, not operational',()=>{
 render(<ObservationBadge monitor={{status:'UP',last_observed_status:'UP',freshness:'STALE',effective_status:'UNKNOWN'}}/>);
 expect(screen.getByText('No recent measurements')).toBeInTheDocument();
 expect(screen.queryByText('Operational')).not.toBeInTheDocument();
});
it('distinguishes paused and awaiting monitors',()=>{
 render(<><ObservationBadge monitor={{status:'PAUSED',freshness:'PAUSED'}}/><ObservationBadge monitor={{status:'UNKNOWN',freshness:'AWAITING'}}/></>);
 expect(screen.getByText('Paused')).toBeInTheDocument();expect(screen.getByText('Awaiting data')).toBeInTheDocument();
});
it('explains retention and absence of observations',()=>{
 render(<HistoryNotice history={{requested_start:'2026-10-19',requested_end:'2026-11-19',retention_days:7,retention_limited:true,first_check_at:null,last_check_at:null,completed_checks:0}}/>);
 expect(screen.getByRole('note')).toHaveTextContent('exceeds 7-day retention');
 expect(screen.getByRole('note')).toHaveTextContent('No measurements');
 expect(screen.getByRole('note')).toHaveTextContent('not elapsed uptime');
});
