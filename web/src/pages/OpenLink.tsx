import type { ProjectType, Status } from "../api";
import { AppLink, Failed, Loading, Notice, PageHead, StatusTag, Tags } from "../components/ui";
import { useApp } from "../context";
import { teamSize } from "../format";
import { useLoad } from "../hooks";
import { SubmitForm } from "./Submit";

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
    top = <SubmitForm code={code} faculty={link.faculty} minTeam={link.min_members} maxTeam={link.max_members} />;
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
