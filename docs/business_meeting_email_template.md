# Mail-merge template — business-meeting slides (chairs 2022–2026)

Data source: `docs/business_meeting_mailmerge_2022-2026.csv`
«field» = Word merge field (Mailings → Insert Merge Field). Everything else is literal text.

---

**To:** «email»

**Subject:** Your «editions_short» business-meeting slides — for QuantumDB

Dear «first_name»,

I'm writing on behalf of QuantumDB (https://quantumdb.iaqi.org), an open community database, run under IAQI, that documents the QIP, QCrypt and TQC conference series: their talks, authors, and program, organizing and steering committees over the full history of each series.

We are now adding, for every edition, the statistics presented at the business meeting — submissions, accepted talks and posters, acceptance rates, registered and on-site participants, countries represented — together with links to the business-meeting slides themselves (typically the PC-chair report and the local-organizers report).

You served as «editions». Would you still have the slides you presented or received at the business meeting? Anything helps:

- the slide decks as PDF, or a link to where they are hosted;
- if the slides are gone, the headline numbers you remember or can look up;
- or a pointer to a co-chair or organizer who might still have them.

We record the source of every figure, and the compiled statistics will be freely available on the site for the community.

«IF current_sc_chair = "yes"»As a current steering-committee chair, you may also know where reports from earlier editions are archived — a pointer to a shared drive or to past chairs would be very welcome.«ENDIF»

Thank you very much for your help, and for the work you put into the conference.

Best regards,
Christian Schaffner
QuantumDB / IAQI · https://quantumdb.iaqi.org

---

## Word notes

- **Conditional paragraph:** Mailings → Rules → *If…Then…Else…* → field `current_sc_chair`, *Equal to*, `yes`; paste the steering-committee sentence as the "insert this text" value and leave "otherwise" empty. (Or just delete that paragraph and send the five SC chairs a separate version.)
- **Subject line:** Word's *Merge to Email* dialog takes plain text only — no merge fields. Either use a fixed subject (e.g. `Business-meeting slides for QuantumDB`) or, to keep «editions_short» in the subject, use an add-in / the Outlook "Mail Merge" tool.
- Drop rows with an empty `email` (Jordan, Elkouss, del Rio) before merging, or fill them in.
- Send to yourself first: temporarily put your own address in the first row and merge only record 1.
