import { useEffect, useRef, useState } from 'react';
import {
  ArrowClockwiseIcon,
  CaretDownIcon,
  CircleNotchIcon,
  ClockCounterClockwiseIcon,
  DiceFiveIcon,
  UserMinusIcon,
  UserPlusIcon,
  WarningIcon,
} from '@phosphor-icons/react';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Segmented } from '@/components/ui/segmented';
import { Notice } from '@/components/common/Notice';
import { PageHeading, SectionTitle } from '@/components/common/Text';
import {
  ACCESS_TEXT_OTHER,
  ActivityList,
  Field,
  fmtIstWhen,
  generatePassword,
  HandoverCard,
  INPUT_CLASS,
  INVALID_CLASS,
  ROLE_OPTIONS,
  RoleBadge,
} from '@/components/account/AccountParts';
import { api } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { useApiData } from '@/lib/hooks';
import { cn } from '@/lib/utils';

// Typed passwords are shown in clear (they are handed over), so keep browsers from saving or fixing them.
const PLAIN_PASSWORD_PROPS = {
  type: 'text',
  autoComplete: 'off',
  autoCapitalize: 'none',
  autoCorrect: 'off',
  spellCheck: false,
};

function passwordProblem(pw) {
  if (pw.length < 8) return 'Use at least 8 characters, or tap Generate.';
  if (pw.length > 128) return 'Use 128 characters or fewer.';
  return null;
}

// The order the server sends: the super admin first, then by name.
function sortPeople(list) {
  const rank = (p) => (p.role === 'super_admin' ? 0 : 1);
  return [...list].sort((a, b) => rank(a) - rank(b) || a.name.localeCompare(b.name));
}

/** Onboard people and manage everyone's access. Super admin only (the router keeps others out). */
export function UsersScreen() {
  const { user: me } = useAuth();
  const people = useApiData('/users');
  const [openId, setOpenId] = useState(null);
  const [removed, setRemoved] = useState(null);

  const added = (u) => {
    setRemoved(null);
    people.setData((list) => sortPeople([...(list || []).filter((p) => p.id !== u.id), u]));
  };
  const patch = (id, fields) => people.setData((list) => (list || []).map((p) => (p.id === id ? { ...p, ...fields } : p)));
  const drop = (person) => {
    people.setData((list) => (list || []).filter((p) => p.id !== person.id));
    setOpenId(null);
    setRemoved(person.name);
  };

  const list = people.data || [];

  return (
    <div className="max-w-2xl space-y-10 lg:max-w-none">
      <PageHeading eyebrow="Users" title="People" subtitle="Who can sign in, and what each person can do. Only you see this page." />

      {/* Phones: the form first, then everyone. Wide screens: the list on the left, the form beside it. */}
      <div className="grid gap-10 lg:grid-cols-[minmax(0,7fr)_minmax(0,5fr)] lg:gap-12">
        <section className="space-y-3 lg:col-start-2 lg:row-start-1">
          <SectionTitle title="Onboard someone" hint="They sign in with the email and password you set here." />
          <OnboardForm onAdded={added} />
        </section>

        <section className="space-y-3 lg:col-start-1 lg:row-start-1">
          <SectionTitle
            title={people.data ? `People · ${list.length}` : 'People'}
            hint="Select someone to change their access, set a new password, see their activity or remove them."
          >
            {people.loading && people.data && <CircleNotchIcon weight="bold" className="h-4 w-4 animate-spin text-muted-foreground" />}
          </SectionTitle>

          {removed && <Notice tone="success" title={`${removed} was removed.`}>They can no longer sign in.</Notice>}

          {people.error && (
            <Notice
              tone="error"
              title="Could not load people"
              action={
                <Button variant="outline" size="touch" onClick={people.reload}>
                  <ArrowClockwiseIcon weight="bold" />
                  Try again
                </Button>
              }
            >
              {people.error.message}
            </Notice>
          )}

          {!people.data && people.loading && (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <CircleNotchIcon weight="bold" className="h-4 w-4 animate-spin" /> Loading people
            </div>
          )}

          {list.length > 0 && (
            <Card className="divide-y divide-border overflow-hidden">
              {list.map((p) => {
                const locked = p.id === me?.id || p.role === 'super_admin';
                const open = !locked && openId === p.id;
                return (
                  <div key={p.id}>
                    <PersonRow
                      person={p}
                      isMe={p.id === me?.id}
                      locked={locked}
                      open={open}
                      onToggle={() => {
                        setRemoved(null);
                        setOpenId(open ? null : p.id);
                      }}
                    />
                    {open && <PersonPanel key={p.id} person={p} onPatch={patch} onRemoved={drop} />}
                  </div>
                );
              })}
            </Card>
          )}

          {people.data && list.length <= 1 && <p className="text-sm text-muted-foreground">No one else yet.</p>}
        </section>
      </div>
    </div>
  );
}

// ---- onboarding -------------------------------------------------------------------------------

const EMPTY_FORM = { name: '', email: '', password: '', role: 'viewer' };

function OnboardForm({ onAdded }) {
  const [form, setForm] = useState(EMPTY_FORM);
  const [errors, setErrors] = useState({});
  const [state, setState] = useState({ status: 'idle' }); // idle | saving | error
  const [handover, setHandover] = useState(null);
  const handoverRef = useRef(null);
  const saving = state.status === 'saving';

  // On a phone the card sits above the form, likely scrolled out of view by now.
  useEffect(() => {
    if (handover) handoverRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }, [handover]);

  const set = (key, value) => {
    setForm((f) => ({ ...f, [key]: value }));
    setErrors((e) => ({ ...e, [key]: null }));
    if (!saving) setState({ status: 'idle' });
  };

  const submit = async (e) => {
    e.preventDefault();
    if (saving) return;
    const name = form.name.trim();
    const email = form.email.trim();
    const errs = {
      name: name ? null : 'Enter their name.',
      email: !email ? 'Enter their email.' : /^[^\s@]+@[^\s@]+$/.test(email) ? null : 'This does not look like an email address.',
      password: passwordProblem(form.password),
    };
    setErrors(errs);
    if (Object.values(errs).some(Boolean)) return;

    setState({ status: 'saving' });
    try {
      const res = await api('/users', { method: 'POST', json: { name, email, password: form.password, role: form.role } });
      setHandover({ name: res.user?.name || name, email: res.user?.email || email, password: form.password });
      setForm(EMPTY_FORM);
      setState({ status: 'idle' });
      if (res.user) onAdded(res.user);
    } catch (err) {
      if (err.status === 409) {
        setErrors((s) => ({ ...s, email: err.message }));
        setState({ status: 'idle' });
      } else {
        setState({ status: 'error', error: err.message });
      }
    }
  };

  return (
    <div className="space-y-3">
      {handover && (
        <div ref={handoverRef} className="scroll-mt-24">
          <HandoverCard
            title={`Give ${handover.name} these to sign in`}
            email={handover.email}
            password={handover.password}
            note="Shown only now. They can change the password from Account after signing in."
            onDismiss={() => setHandover(null)}
          />
        </div>
      )}

      <Card className="px-4 py-4 md:px-5">
        <form onSubmit={submit} noValidate className="space-y-4">
          <Field id="new-name" label="Name" error={errors.name}>
            <input
              id="new-name"
              type="text"
              value={form.name}
              onChange={(e) => set('name', e.target.value)}
              maxLength={80}
              autoComplete="off"
              autoCapitalize="words"
              enterKeyHint="next"
              aria-invalid={!!errors.name || undefined}
              aria-describedby="new-name-note"
              className={cn(INPUT_CLASS, errors.name && INVALID_CLASS)}
            />
          </Field>

          <Field id="new-email" label="Email" error={errors.email} hint="Used to sign in. It can't be changed later.">
            <input
              id="new-email"
              type="email"
              inputMode="email"
              value={form.email}
              onChange={(e) => set('email', e.target.value)}
              autoComplete="off"
              autoCapitalize="none"
              autoCorrect="off"
              spellCheck={false}
              enterKeyHint="next"
              aria-invalid={!!errors.email || undefined}
              aria-describedby="new-email-note"
              className={cn(INPUT_CLASS, errors.email && INVALID_CLASS)}
            />
          </Field>

          <Field id="new-password" label="Password" error={errors.password} hint="At least 8 characters. You hand this to them.">
            <div className="flex gap-2">
              <input
                id="new-password"
                {...PLAIN_PASSWORD_PROPS}
                value={form.password}
                onChange={(e) => set('password', e.target.value)}
                aria-invalid={!!errors.password || undefined}
                aria-describedby="new-password-note"
                className={cn(INPUT_CLASS, 'font-mono tracking-wide', errors.password && INVALID_CLASS)}
              />
              <Button type="button" variant="outline" size="touch" className="shrink-0 md:h-10" onClick={() => set('password', generatePassword())}>
                <DiceFiveIcon weight="bold" />
                Generate
              </Button>
            </div>
          </Field>

          <div className="space-y-1.5">
            <div className="text-sm font-medium">Access</div>
            <Segmented aria-label="Access" options={ROLE_OPTIONS} value={form.role} onChange={(v) => set('role', v)} />
            <p className="text-xs text-muted-foreground">{ACCESS_TEXT_OTHER[form.role]}</p>
          </div>

          {state.status === 'error' && (
            <Notice tone="error" title="Not added">
              {state.error}
            </Notice>
          )}

          <Button type="submit" size="touch" className="w-full sm:w-auto" disabled={saving}>
            {saving ? <CircleNotchIcon weight="bold" className="animate-spin" /> : <UserPlusIcon weight="bold" />}
            {saving ? 'Adding' : 'Add'}
          </Button>
        </form>
      </Card>
    </div>
  );
}

// ---- the list --------------------------------------------------------------------------------

function PersonRow({ person, isMe, locked, open, onToggle }) {
  const content = (
    <>
      <span className="min-w-0 flex-1">
        <span className="flex min-w-0 items-center gap-2">
          <span className="truncate text-sm font-medium">{person.name}</span>
          {isMe && (
            <span className="shrink-0 rounded bg-muted px-1.5 py-px text-[11px] font-medium text-muted-foreground">You</span>
          )}
        </span>
        <span className="block truncate text-xs text-muted-foreground">{person.email}</span>
        <span className="block text-xs text-muted-foreground tabular">
          {person.lastLoginAt ? `Last signed in ${fmtIstWhen(person.lastLoginAt)}` : 'Never signed in'}
        </span>
      </span>
      <RoleBadge role={person.role} className="mt-0.5" />
      {locked ? (
        <span className="w-4 shrink-0" aria-hidden />
      ) : (
        <CaretDownIcon
          weight="bold"
          className={cn('mt-0.5 h-4 w-4 shrink-0 text-muted-foreground transition-transform', open && 'rotate-180')}
        />
      )}
    </>
  );
  const row = 'flex min-h-11 w-full items-start gap-3 px-4 py-3 text-left md:px-5';

  if (locked) return <div className={row}>{content}</div>;
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-expanded={open}
      aria-controls={`person-${person.id}`}
      className={cn(
        row,
        'transition-colors hover:bg-accent/50 focus-visible:bg-accent/50 focus-visible:outline-none',
        open && 'bg-accent/40'
      )}
    >
      {content}
    </button>
  );
}

/** Everything the super admin can do for one person. Mounted fresh for each person opened. */
function PersonPanel({ person, onPatch, onRemoved }) {
  const id = person.id;
  const [activityOpen, setActivityOpen] = useState(false);
  const activity = useApiData(activityOpen ? `/users/${id}/activity?limit=50` : null);

  // Access: shown changed at once, put back if the server says no.
  const [role, setRole] = useState({ saving: false, error: null });
  const changeRole = async (next) => {
    if (next === person.role || role.saving) return;
    const before = person.role;
    onPatch(id, { role: next });
    setRole({ saving: true, error: null });
    try {
      const res = await api(`/users/${id}`, { method: 'PATCH', json: { role: next } });
      if (res.user) onPatch(id, res.user);
      setRole({ saving: false, error: null });
      activity.reload();
    } catch (err) {
      onPatch(id, { role: before });
      setRole({ saving: false, error: err.message });
    }
  };

  // New password (forgotten password).
  const [pw, setPw] = useState('');
  const [pwState, setPwState] = useState({ status: 'idle' }); // idle | saving | error
  const [handover, setHandover] = useState(null);
  const savingPw = pwState.status === 'saving';
  const savePassword = async (e) => {
    e.preventDefault();
    if (savingPw) return;
    const problem = passwordProblem(pw);
    if (problem) {
      setPwState({ status: 'error', error: problem });
      return;
    }
    setPwState({ status: 'saving' });
    try {
      await api(`/users/${id}/password`, { method: 'POST', json: { password: pw } });
      setHandover(pw);
      setPw('');
      setPwState({ status: 'idle' });
      activity.reload();
    } catch (err) {
      setPwState({ status: 'error', error: err.message });
    }
  };

  // Remove, after an inline confirm.
  const [confirming, setConfirming] = useState(false);
  const [removeState, setRemoveState] = useState({ status: 'idle' }); // idle | removing | error
  const remove = async () => {
    setRemoveState({ status: 'removing' });
    try {
      await api(`/users/${id}`, { method: 'DELETE' });
      onRemoved(person);
    } catch (err) {
      setRemoveState({ status: 'error', error: err.message });
    }
  };

  const roleCanChange = person.role === 'admin' || person.role === 'viewer';

  return (
    <div id={`person-${id}`} className="space-y-6 border-t border-border bg-muted/30 px-4 pb-5 pt-4 md:px-5">
      {roleCanChange && (
        <div className="space-y-1.5">
          <div className="flex items-center gap-2 text-sm font-medium">
            Access
            {role.saving && <CircleNotchIcon weight="bold" className="h-3.5 w-3.5 animate-spin text-muted-foreground" />}
          </div>
          <div className={cn(role.saving && 'pointer-events-none opacity-60')}>
            <Segmented aria-label={`Access for ${person.name}`} options={ROLE_OPTIONS} value={person.role} onChange={changeRole} />
          </div>
          {role.error ? (
            <p role="alert" className="text-xs text-attention">
              Access not changed. {role.error}
            </p>
          ) : (
            <p className="text-xs text-muted-foreground">{ACCESS_TEXT_OTHER[person.role]}</p>
          )}
        </div>
      )}

      <div className="space-y-3">
        <form onSubmit={savePassword} noValidate>
          <Field
            id={`pw-${id}`}
            label="Set new password"
            error={pwState.status === 'error' ? pwState.error : null}
            hint="For when they forget theirs. Saving signs them out on every device."
          >
            <div className="flex flex-col gap-2 sm:flex-row">
              <input
                id={`pw-${id}`}
                {...PLAIN_PASSWORD_PROPS}
                value={pw}
                onChange={(e) => {
                  setPw(e.target.value);
                  if (!savingPw) setPwState({ status: 'idle' });
                }}
                aria-invalid={pwState.status === 'error' || undefined}
                aria-describedby={`pw-${id}-note`}
                className={cn(INPUT_CLASS, 'font-mono tracking-wide', pwState.status === 'error' && INVALID_CLASS)}
              />
              <div className="grid shrink-0 grid-cols-2 gap-2 sm:flex">
                <Button
                  type="button"
                  variant="outline"
                  size="touch"
                  className="md:h-10"
                  onClick={() => {
                    setPw(generatePassword());
                    setPwState({ status: 'idle' });
                  }}
                >
                  <DiceFiveIcon weight="bold" />
                  Generate
                </Button>
                <Button type="submit" size="touch" className="md:h-10" disabled={!pw || savingPw}>
                  {savingPw && <CircleNotchIcon weight="bold" className="animate-spin" />}
                  {savingPw ? 'Saving' : 'Save'}
                </Button>
              </div>
            </div>
          </Field>
        </form>
        {handover && (
          <HandoverCard
            title={`Give ${person.name} this new password`}
            email={person.email}
            password={handover}
            note="They were signed out on every device and need this to sign in again."
            onDismiss={() => setHandover(null)}
          />
        )}
      </div>

      <div className="space-y-2">
        <Button
          type="button"
          variant="outline"
          size="touch"
          className="w-full bg-transparent sm:w-auto"
          aria-expanded={activityOpen}
          onClick={() => setActivityOpen((o) => !o)}
        >
          <ClockCounterClockwiseIcon weight="bold" />
          {activityOpen ? 'Hide activity' : 'Activity'}
        </Button>
        {activityOpen && (
          <div className="space-y-2">
            {activity.error && (
              <Notice
                tone="error"
                title="Could not load their activity"
                action={
                  <Button variant="outline" size="touch" className="bg-transparent" onClick={activity.reload}>
                    <ArrowClockwiseIcon weight="bold" />
                    Try again
                  </Button>
                }
              >
                {activity.error.message}
              </Notice>
            )}
            {!activity.data && activity.loading && (
              <div className="flex items-center gap-2 py-2 text-sm text-muted-foreground">
                <CircleNotchIcon weight="bold" className="h-4 w-4 animate-spin" /> Loading
              </div>
            )}
            {activity.data && <ActivityList items={activity.data} pageSize={10} className="pt-1" />}
          </div>
        )}
      </div>

      {!confirming ? (
        <Button
          type="button"
          variant="outline"
          size="touch"
          className="w-full bg-transparent sm:w-auto"
          onClick={() => {
            setRemoveState({ status: 'idle' });
            setConfirming(true);
          }}
        >
          <UserMinusIcon weight="bold" />
          Remove
        </Button>
      ) : (
        <div className="space-y-3 rounded-lg bg-attention/[0.08] px-4 py-3">
          <div className="flex gap-3">
            <WarningIcon weight="fill" className="mt-0.5 h-4 w-4 shrink-0 text-attention" />
            <p className="text-sm font-medium leading-snug">
              Remove {person.name}? They will be signed out and can&apos;t sign in again.
            </p>
          </div>
          {removeState.status === 'error' && (
            <p role="alert" className="text-xs text-attention">
              {removeState.error}
            </p>
          )}
          <div className="grid grid-cols-2 gap-2 sm:flex sm:justify-end">
            <Button
              type="button"
              variant="outline"
              size="touch"
              className="bg-transparent"
              autoFocus
              onClick={() => setConfirming(false)}
              disabled={removeState.status === 'removing'}
            >
              Cancel
            </Button>
            <Button
              type="button"
              size="touch"
              className="bg-attention text-attention-foreground hover:bg-attention/90"
              onClick={remove}
              disabled={removeState.status === 'removing'}
            >
              {removeState.status === 'removing' && <CircleNotchIcon weight="bold" className="animate-spin" />}
              Remove
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
