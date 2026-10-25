import { useState } from "react";
import type { ProjectType, Status } from "../api";
import { AppLink, Failed, Loading, Notice, PageHead, Segmented, StatusTag, Tags } from "../components/ui";
import { useApp } from "../context";
import { teamSize } from "../format";
import { useLoad } from "../hooks";
import { SubmitForm, type SavedProject } from "./Submit";

interface ClassProject {
  project_id: number;
  title: string;
  members: string | null;
  status: Status;
  project_type: ProjectType;
  tags: string[];
  mine: boolean;
}

interface OpenLinkData {
  submission_link_id: number;
  faculty: string;
  subject: string;
  subject_name: string;
  academic_year: string;
  class_name: string;
  purpose: string;
  max_marks: number;
  min_members: number;
  max_members: number | null;
  is_open: boolean;
  waiting: number;
  projects: ClassProject[];
  my_project: number | null;
  is_owner: boolean;
  saved: SavedProject[];
}

const WAYS = ["new", "saved"] as const;
const WAY_NAMES = { new: "Submit a new project", saved: "Submit a saved project" };

// A team either fills in a new project, or picks one of its projects from another
// link (LCA 1 going on to LCA 2) and the form starts from that.
function Submitting({ code, link }: { code: string; link: OpenLinkData }) {
  const [way, setWay] = useState<(typeof WAYS)[number]>("new");
  const [picked, setPicked] = useState<SavedProject | null>(null);
  const form = { code, faculty: link.faculty, minTeam: link.min_members, maxTeam: link.max_members };
  return (
    <div className="stack" style={{ gap: 14 }}>
      <div><Segmented options={WAYS} value={way} onChange={setWay} label="New or saved project" names={WAY_NAMES} /></div>
      {way === "new" && <SubmitForm {...form} />}
      {way === "saved" && link.saved.length === 0 && (
        <div className="empty">You have no saved projects yet. Projects your team submits through other links show up here.</div>
      )}
      {way === "saved" && link.saved.length > 0 && (
        <>
          <div className="stack-sm" role="radiogroup" aria-label="Saved projects">
            {link.saved.map((p) => (
              <button key={p.project_id} type="button" role="radio" aria-checked={picked?.project_id === p.project_id}
                      className={`card pad stack-sm row-link${picked?.project_id === p.project_id ? " on" : ""}`}
                      style={{ textAlign: "left" }} onClick={() => setPicked(p)}>
                <div className="row-top" style={{ gap: 12 }}>
                  <div className="grow">
                    <div className="strong title">{p.title}</div>
                    <div className="meta">{[p.subject, p.purpose, p.academic_year].join(" · ")}</div>
                  </div>
                  <StatusTag status={p.status} />
                </div>
              </button>
            ))}
          </div>
          {picked ? <SubmitForm key={picked.project_id} {...form} from={picked} />
                  : <div className="small muted">Pick the project to submit here. You can change anything before you send it.</div>}
        </>
      )}
    </div>
  );
}

// A submission link as the class opens it: what it is for, the submit form (until the
// student's team has a project here), and the class's projects so far.
export default function OpenLink({ code }: { code: string }) {
  const { me, go } = useApp();
  const { data: link, error, loading, reload } = useLoad<OpenLinkData>(`/s/${code}`);
  if (loading && !link) return <><PageHead title="Submission link" /><Loading /></>;
  if (error || !link) return <><PageHead title="Submission link" /><Failed message={error ?? ""} retry={reload} /></>;

  const mine = link.projects.find((p) => p.project_id === link.my_project);
  const others = link.projects.filter((p) => p.project_id !== link.my_project);
  // Other teams' projects waiting for review aren't listed, only counted.
  const hidden = link.waiting - link.projects.filter((p) => p.status === "submitted").length;
  let top;
  if (link.is_owner) {
    top = (
      <Notice tone="info">
        This is your link. <button className="link" onClick={() => go(`/links/${link.submission_link_id}`)}>Review and grade its projects</button>
      </Notice>
    );
  } else if (me.role !== "student") {
    top = <Notice tone="info">Students of {link.class_name} submit their projects here.</Notice>;
  } else if (mine) {
    top = (
      <Notice tone="up">
        Your team has submitted <AppLink to={`/projects/${mine.project_id}`}>{mine.title}</AppLink> here.{" "}
        {mine.status === "submitted" ? `${link.faculty} hasn't reviewed it yet.` : "It has been approved."}{" "}
        A student has one project in each submission link, so there is no form to fill in; your team can submit
        again only if this one is rejected. Its links and files can still be changed on the project page.
      </Notice>
    );
  } else if (!link.is_open) {
    top = <Notice tone="warn">This link is closed, so it takes no new projects. Ask {link.faculty} if you still need to submit.</Notice>;
  } else {
    top = <Submitting code={code} link={link} />;
  }

  return (
    <>
      <PageHead title={`${link.purpose} · ${link.subject}`}
                sub={[link.subject_name, link.class_name, link.faculty, link.academic_year, `each student out of ${link.max_marks}`,
                      teamSize(link.min_members, link.max_members)].filter(Boolean).join(" · ")} />
      <div className="stack" style={{ gap: 20 }}>
        {top}
        <div className="stack" style={{ gap: 10 }}>
          <div className="label section">
            Projects in this class{hidden > 0 && <span className="muted" style={{ fontWeight: 400 }}> · {hidden} more waiting for review</span>}
          </div>
          {others.map((p) => (
            <AppLink key={p.project_id} to={`/projects/${p.project_id}`} className="card pad stack-sm row-link">
              <div className="row-top" style={{ gap: 12 }}>
                <div className="grow">
                  <div className="strong title">{p.title}</div>
                  {p.members && <div className="meta">{p.members}</div>}
                </div>
                {p.status !== "approved" && <StatusTag status={p.status} />}
              </div>
              <Tags tags={p.tags} type={p.project_type} />
            </AppLink>
          ))}
          {others.length === 0 && <div className="empty">No approved projects here yet.</div>}
        </div>
      </div>
    </>
  );
}
