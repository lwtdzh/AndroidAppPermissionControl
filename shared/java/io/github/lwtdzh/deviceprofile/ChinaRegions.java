package io.github.lwtdzh.deviceprofile;

import java.io.*;
import java.nio.charset.StandardCharsets;
import java.util.*;

/** Offline hierarchy and representative coordinates. */
public final class ChinaRegions {
    public static final class Region {
        public final String id,parent,name,latitude,longitude;
        public Region(String[] row) {
            id=row[0];parent=row[1];name=row[2];longitude=row[3];latitude=row[4];
        }
        public boolean hasPoint(){return !latitude.isEmpty() && !longitude.isEmpty();}
        @Override public String toString(){return name;}
    }
    private final Map<String,Region> regions=new LinkedHashMap<>();
    private final Map<String,List<Region>> children=new LinkedHashMap<>();
    public ChinaRegions(InputStream source)throws IOException {
        try(BufferedReader reader=new BufferedReader(new InputStreamReader(source,StandardCharsets.UTF_8))){
            String line;
            while((line=reader.readLine())!=null){
                String[] row=line.split("\t",-1);
                if(row.length!=5)throw new IOException("Invalid region row");
                Region r=new Region(row);
                if(regions.put(r.id,r)!=null)throw new IOException("Duplicate region");
                children.computeIfAbsent(r.parent,k->new ArrayList<>()).add(r);
            }
        }
    }
    public Region find(String id){return regions.get(id);}
    public List<Region> children(String id){return Collections.unmodifiableList(children.getOrDefault(id,Collections.emptyList()));}
    public String path(Region r){
        LinkedList<String> names=new LinkedList<>();
        for(Region p=r;p!=null;p=regions.get(p.parent))names.addFirst(p.name);
        return String.join(" / ",names);
    }
    public Map<String,String> packet(Region r) {
        if(!r.hasPoint())throw new IllegalArgumentException("Representative coordinates unavailable");
        Map<String,String> values=new LinkedHashMap<>();
        values.put("latitude",r.latitude);values.put("longitude",r.longitude);values.put("accuracy","100");
        return values;
    }
}
