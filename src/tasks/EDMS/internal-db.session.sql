SELECT COUNT(*) AS total_forms
FROM edms.wf_form_data fd
JOIN edms.wf_form f ON fd.form_id = f.id
JOIN edms.form_of_folder ff ON f.id = ff.form_id
JOIN edms.folder_of_dept fod ON ff.folder_id = fod.id
JOIN edms.org_department d ON fod.dept_id = d.id
WHERE f.parent_id IS NULL
AND d.name <> 'Draft'
AND d.name = 'STM'
AND fd.date_create >= DATE_FORMAT(CURDATE(), '%Y-%m-01')
AND fd.date_create <= LAST_DAY(CURDATE());

SELECT 
    d.name AS department,
    COUNT(*) AS total_forms
FROM edms.wf_form_data fd
JOIN edms.wf_form f ON fd.form_id = f.id
JOIN edms.form_of_folder ff ON f.id = ff.form_id
JOIN edms.folder_of_dept fod ON ff.folder_id = fod.id
JOIN edms.org_department d ON fod.dept_id = d.id
WHERE f.parent_id IS NULL
AND d.name <> 'Draft'
AND fd.date_create >= DATE_FORMAT(CURDATE(), '%Y-%m-01')
AND fd.date_create <= LAST_DAY(CURDATE())
GROUP BY d.name
ORDER BY d.name;

SELECT 
    d.name AS department,

    -- tổng form từ trước tới nay
    COUNT(DISTINCT fd.id) AS total_forms_all_time,

    -- tổng form tháng này
    COUNT(DISTINCT CASE 
        WHEN fd.date_create >= DATE_FORMAT(CURDATE(),'%Y-%m-01')
        AND fd.date_create < DATE_FORMAT(CURDATE() + INTERVAL 1 MONTH,'%Y-%m-01')
        THEN fd.id 
    END) AS total_forms_this_month

FROM edms.wf_form_data fd
JOIN edms.wf_form f ON fd.form_id = f.id
JOIN edms.form_of_folder ff ON f.id = ff.form_id
JOIN edms.folder_of_dept fod ON ff.folder_id = fod.id
JOIN edms.org_department d ON fod.dept_id = d.id

WHERE f.parent_id IS NULL
AND d.name <> 'Draft'

GROUP BY d.name;



SELECT 
    d.name AS department,

    -- tổng form từ trước tới nay
    COUNT(DISTINCT fd.id) AS total_forms_all_time,

    -- tổng form tháng này
    COUNT(DISTINCT CASE 
        WHEN fd.date_create >= DATE_FORMAT(CURDATE(),'%Y-%m-01')
         AND fd.date_create < DATE_FORMAT(CURDATE() + INTERVAL 1 MONTH,'%Y-%m-01')
        THEN fd.id
    END) AS total_forms_this_month,

    -- tổng form năm 2025
    COUNT(DISTINCT CASE 
        WHEN fd.date_create >= '2025-01-01'
         AND fd.date_create < '2026-01-01'
        THEN fd.id
    END) AS total_forms_2025

FROM edms.wf_form_data fd
JOIN edms.wf_form f ON fd.form_id = f.id
JOIN edms.form_of_folder ff ON f.id = ff.form_id
JOIN edms.folder_of_dept fod ON ff.folder_id = fod.id
JOIN edms.org_department d ON fod.dept_id = d.id

WHERE f.parent_id IS NULL
AND d.name NOT IN ('Draft','PRESS','LEAD_CREW')

GROUP BY d.name
ORDER BY total_forms_2025 DESC;

