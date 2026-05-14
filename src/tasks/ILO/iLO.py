import json
import redfish
from redfish.rest.v1 import ServerDownOrUnreachableError
import pandas as pd
from datetime import datetime
import os
import subprocess

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

# ==========================================
# CẤU HÌNH EMAIL
# ==========================================
GMAIL_USER = "noreply.nivs@gmail.com"
GMAIL_APP_PASSWORD = "jjxpgndrikbftwed"
GMAIL_TO = [
    "hai.tranviet@nidec.com",
    "phu.truongvan@nidec.com",
    "binh.lethai@nidec.com",
]

def get_ilo5_health_summary(ilo_host, ilo_username, ilo_password, server_name, df):
    # Initialize dictionary to store results
    health_summary = {
        "Server Name": server_name,
        "IP Address": ilo_host,
        "Agentless Management Service": "Not available",
        "BIOS/Hardware Health": "N/A",
        "Fan Redundancy": "N/A",
        "Fans": "N/A",
        "Memory": "N/A",
        "Network": "N/A",
        "Power Status": "N/A",
        "Power Supplies": "N/A",
        "Processors": "N/A",
        "Smart Storage Energy Pack": "N/A",
        "Storage": "N/A",
        "Temperatures": "N/A"
    }

    # Establish connection to iLO
    try:
        print(f"INFO: Connecting to iLO at {ilo_host} for server: {server_name}")
        redfish_client = redfish.RedfishClient(base_url=f"https://{ilo_host}",
                                               username=ilo_username,
                                               password=ilo_password,
                                               timeout=3) # Adding a timeout
        redfish_client.login()
        print(f"INFO: Successfully connected to iLO at {ilo_host}")
    except ServerDownOrUnreachableError:
        print(f"ERROR: Cannot connect to iLO at {ilo_host}. Server is down or unreachable.")
        health_summary["BIOS/Hardware Health"] = "Connection Failed"
        df = pd.concat([df, pd.DataFrame([health_summary])], ignore_index=True)
        return df
    except Exception as e:
        print(f"ERROR: {ilo_host} login error: {type(e).__name__} - {str(e)}")
        health_summary["BIOS/Hardware Health"] = "Login Failed"
        df = pd.concat([df, pd.DataFrame([health_summary])], ignore_index=True)
        return df

    try:
        res = redfish_client.post("/redfish/v1/Views", body={"Select":[{"From":"/Systems/1/","Properties":["Oem.Hpe.AggregateHealthStatus as Health","PowerState AS PowerState","Oem.Hpe.PostState as PostState"]}]})
        if res.status == 200:
            data = res.dict
            print(f"INFO: Successfully retrieved data for {server_name} ({ilo_host})")

            # Extract information from Health
            health_data = data.get("Health", {})

            # Map values to health_summary
            health_summary["Agentless Management Service"] = "Not available" if health_data.get("AgentlessManagementService") == "Unavailable" else health_data.get("AgentlessManagementService", "N/A")
            health_summary["BIOS/Hardware Health"] = health_data.get("BiosOrHardwareHealth", {}).get("Status", {}).get("Health", "N/A")
            health_summary["Fan Redundancy"] = health_data.get("FanRedundancy", "N/A")
            health_summary["Fans"] = health_data.get("Fans", {}).get("Status", {}).get("Health", "N/A")
            health_summary["Memory"] = health_data.get("Memory", {}).get("Status", {}).get("Health", "N/A")
            health_summary["Network"] = health_data.get("Network", {}).get("Status", {}).get("Health", "N/A")
            health_summary["Power Status"] = health_data.get("PowerSupplyRedundancy", "N/A")
            health_summary["Power Supplies"] = health_data.get("PowerSupplies", {}).get("Status", {}).get("Health", "N/A")
            health_summary["Processors"] = health_data.get("Processors", {}).get("Status", {}).get("Health", "N/A")
            health_summary["Smart Storage Energy Pack"] = health_data.get("SmartStorageBattery", {}).get("Status", {}).get("Health", "N/A")
            health_summary["Storage"] = health_data.get("Storage", {}).get("Status", {}).get("Health", "N/A")
            health_summary["Temperatures"] = health_data.get("Temperatures", {}).get("Status", {}).get("Health", "N/A")

            # Append results to DataFrame
            df = pd.concat([df, pd.DataFrame([health_summary])], ignore_index=True)
        else:
            print(f"ERROR: Error retrieving data from iLO {ilo_host}: {res.status} - {res.text}")
            health_summary["BIOS/Hardware Health"] = f"Data Retrieval Error: {res.status}"
            df = pd.concat([df, pd.DataFrame([health_summary])], ignore_index=True)

    except json.JSONDecodeError as e:
        print(f"ERROR: JSON parsing error for {ilo_host}: {str(e)}")
    except Exception as e:
        print(f"ERROR: Error processing data for {ilo_host}: {str(e)}")
    finally:
        print(f"INFO: Logging out from {ilo_host}")
        redfish_client.logout()

    return df

def send_server_alert_email(df, excel_path):
    if df.empty:
        print("INFO: Không có dữ liệu Server để gửi mail.")
        return

    msg = MIMEMultipart()
    msg["From"] = GMAIL_USER
    msg["To"] = ", ".join(GMAIL_TO)

    # Đánh giá tổng quan: Nếu có bất kỳ lỗi kết nối hoặc phần cứng nào (khác OK và N/A) -> Báo Đỏ
    has_error = False
    for _, row in df.iterrows():
        bios_health = str(row.get("BIOS/Hardware Health", ""))
        if "Failed" in bios_health or "Error" in bios_health or "Critical" in bios_health or "Warning" in bios_health:
            has_error = True
            break

    if has_error:
        msg["Subject"] = f"🔴 BÁO CÁO KIỂM TRA SỨC KHỎE SERVER"
    else:
        msg["Subject"] = "🟢 [BÁO CÁO] Hệ thống Máy chủ (Server) hoạt động bình thường 100%"

    # ==========================================
    # XÂY DỰNG GIAO DIỆN BẢNG HTML CHO EMAIL
    # ==========================================
    html_body = f"""
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; color: #333; }}
            /* Thiết lập cuộn ngang nếu bảng quá rộng trên màn hình nhỏ */
            .table-container {{ overflow-x: auto; width: 100%; }}
            table {{ border-collapse: collapse; width: 100%; margin-bottom: 20px; white-space: nowrap; }}
            /* Giảm font chữ và padding để nhét vừa 15 cột */
            th, td {{ border: 1px solid #dddddd; text-align: center; padding: 6px 4px; font-size: 12px; }}
            th {{ background-color: #f4f4f4; color: #000; font-weight: bold; }}
            .text-left {{ text-align: left; }}
            .status-ok {{ color: #008000; font-weight: bold; }}
            .status-ng {{ color: #d93025; font-weight: bold; }}
            .status-warn {{ color: #ff8c00; font-weight: bold; }}
            .header-box {{ background-color: #004a99; color: white; padding: 15px; text-align: center; margin-bottom: 20px; }}
        </style>
    </head>
    <body>
        <div class="header-box">
            <h2 style="margin: 0;">BÁO CÁO TỔNG HỢP SỨC KHỎE MÁY CHỦ (iLO)</h2>
            <p style="margin: 5px 0 0 0;">Thời gian quét: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}</p>
        </div>

        <div class="table-container">
            <table>
                <tr>
                    <th>STT</th>
                    <th class="text-left">Tên Máy Chủ</th>
                    <th>IP iLO</th>
                    <th>AMS</th>
                    <th>BIOS/HW</th>
                    <th>Fan Redundancy</th>
                    <th>Fans</th>
                    <th>Memory</th>
                    <th>Network</th>
                    <th>Power Status</th>
                    <th>Power Supplies</th>
                    <th>Processors</th>
                    <th>Smart Storage</th>
                    <th>Storage</th>
                    <th>Temperatures</th>
                </tr>
    """

    # Hàm phụ để tự động tô màu các trạng thái của HP iLO
    def get_color_class(status):
        status = str(status).strip()
        if status in ["OK", "Good"]: return "status-ok"
        if status in ["Warning", "Degraded"]: return "status-warn"
        if status in ["N/A", "Not available", "Unavailable"]: return ""
        return "status-ng" # Các lỗi Failed, Critical, Connection Failed...

    # Lặp qua DataFrame để tạo các hàng trong bảng
    for i, row in df.iterrows():
        # Lấy toàn bộ 14 thông số
        name = row.get("Server Name", "Unknown")
        ip = row.get("IP Address", "Unknown")
        ams = str(row.get("Agentless Management Service", "N/A"))
        bios = str(row.get("BIOS/Hardware Health", "N/A"))
        fan_red = str(row.get("Fan Redundancy", "N/A"))
        fans = str(row.get("Fans", "N/A"))
        mem = str(row.get("Memory", "N/A"))
        net = str(row.get("Network", "N/A"))
        pwr_stat = str(row.get("Power Status", "N/A"))
        pwr_sup = str(row.get("Power Supplies", "N/A"))
        cpu = str(row.get("Processors", "N/A"))
        smart_stg = str(row.get("Smart Storage Energy Pack", "N/A"))
        storage = str(row.get("Storage", "N/A"))
        temp = str(row.get("Temperatures", "N/A"))

        html_body += f"""
                <tr>
                    <td>{i+1}</td>
                    <td class="text-left"><b>{name}</b></td>
                    <td><code>{ip}</code></td>
                    <td class="{get_color_class(ams)}">{ams}</td>
                    <td class="{get_color_class(bios)}">{bios}</td>
                    <td class="{get_color_class(fan_red)}">{fan_red}</td>
                    <td class="{get_color_class(fans)}">{fans}</td>
                    <td class="{get_color_class(mem)}">{mem}</td>
                    <td class="{get_color_class(net)}">{net}</td>
                    <td class="{get_color_class(pwr_stat)}">{pwr_stat}</td>
                    <td class="{get_color_class(pwr_sup)}">{pwr_sup}</td>
                    <td class="{get_color_class(cpu)}">{cpu}</td>
                    <td class="{get_color_class(smart_stg)}">{smart_stg}</td>
                    <td class="{get_color_class(storage)}">{storage}</td>
                    <td class="{get_color_class(temp)}">{temp}</td>
                </tr>
        """

    html_body += """
            </table>
        </div>
        <p style="color: #666; font-style: italic;">* Xem chi tiết đầy đủ trong file Excel đính kèm.</p>
    </body>
    </html>
    """
    
    msg.attach(MIMEText(html_body, "html"))

    # ==========================================
    # ĐÍNH KÈM FILE EXCEL VÀO EMAIL
    # ==========================================
    if os.path.exists(excel_path):
        try:
            with open(excel_path, "rb") as f:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", f"attachment; filename={os.path.basename(excel_path)}")
            msg.attach(part)
        except Exception as e:
            print(f"ERROR: Lỗi đính kèm file Excel: {e}")

    # Gửi mail
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_USER, GMAIL_TO, msg.as_string())
        print("\n>>> Đã gửi email báo cáo Server thành công!")
    except Exception as e:
        print(f"\n>>> ERROR: Lỗi khi gửi email: {e}")

if __name__ == "__main__":
    # Generate the current date in yyyymmdd format
    current_date = datetime.now().strftime("%Y%m%d")

    print("--- Starting iLO Health Check Script ---")

    # Load the Excel file
    try:
        print("INFO: Loading server list from Excel file...")
        df = pd.read_excel(r"D:\Automation\src\tasks\ILO\data\ILO Server.xlsx")
        df = df.dropna(axis=0, how='all')
        df = df.dropna(axis=1, how='any')
        df.columns = df.iloc[0]
        df = df.drop(df.index[0])
        print(f"INFO: Successfully loaded {len(df)} servers from file.")
    except FileNotFoundError:
        print(r"ERROR: Excel file not found at D:\Automation\src\tasks\ILO\data\ILO Server.xlsx")
        exit()
    except Exception as e:
        print(f"ERROR: Error loading or parsing Excel file: {e}")
        exit()


    # Create an empty DataFrame to store results
    result_df = pd.DataFrame()

    # Iterate over rows
    for index, row in df.iterrows():
        server_name = row.get('Server Name', f'Unknown Server in row {index}')
        try:
            print(f"INFO: Processing server: {server_name}")
            data = row['Notes'].split('\n')
            ip = data[0]
            credentials = data[1].split(':')
            username = credentials[1].strip("-p")
            password = credentials[2].strip()

            # Call the function and update the result DataFrame
            result_df = get_ilo5_health_summary(ip, username, password, server_name, result_df)
        except Exception as e:
            print(f"ERROR: Error processing row for server '{server_name}': {str(e)}")
            # Add a row to the result to indicate failure for this server
            error_summary = {"Server Name": server_name, "IP Address": ip if 'ip' in locals() else 'N/A', "BIOS/Hardware Health": "Failed to Process Row"}
            result_df = pd.concat([result_df, pd.DataFrame([error_summary])], ignore_index=True)


    # Save the result to an Excel file
    try:
        output_path = rf"N:\Ｃ：ＮＩＶＳ総務・人事(GA&HR)\０４：ＩＴ\１７：RPA Report\2. Server\{current_date}.xlsx"
        print(f"INFO: Saving results to {output_path}")
        result_df.to_excel(output_path, index=False)
        print(f"INFO: Results successfully saved.")
        send_server_alert_email(result_df, output_path)
    except Exception as e:
        print(f"ERROR: Failed to save Excel file to {output_path}: {e}")

    print("--- iLO Health Check Script Finished ---")